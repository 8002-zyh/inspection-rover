"""Route file schema, library, and record/playback controller (no serial I/O)."""
import json
import math
import re
import secrets
import threading
import time
import uuid
from pathlib import Path

from .common import now
from .control import HARD_MAX_DUTY, HARD_MAX_REVERSE_DUTY

SCHEMA = 'patrol.route.v1'
_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{2,64}$')


def validate_route(doc):
    if not isinstance(doc, dict):
        raise ValueError('路线必须为对象')
    if doc.get('schema') != SCHEMA:
        raise ValueError('不支持的路线 schema')
    rid = doc.get('id', '')
    if not _ID_RE.fullmatch(rid):
        raise ValueError('无效路线 ID')
    if not isinstance(doc.get('name'), str) or not doc['name'].strip():
        raise ValueError('路线名称无效')
    samples = doc.get('samples')
    if not isinstance(samples, list) or not samples:
        raise ValueError('路线样本不能为空')
    max_duty = float(doc.get('max_duty', HARD_MAX_DUTY))
    if not (0 < max_duty <= HARD_MAX_DUTY):
        raise ValueError('路线 max_duty 超出硬上限')
    last_t = -1.0
    for i, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise ValueError('样本 #%d 无效' % i)
        try:
            t = float(sample['t'])
            duty = float(sample['duty'])
            steering = float(sample['steering'])
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError('样本 #%d 字段错误' % i) from e
        if not all(math.isfinite(v) for v in (t, duty, steering)):
            raise ValueError('样本 #%d 必须为有限数值' % i)
        if t < 0 or t < last_t:
            raise ValueError('样本时间必须单调非降')
        if duty < -HARD_MAX_REVERSE_DUTY or duty > HARD_MAX_DUTY:
            raise ValueError('样本 #%d duty 超限（倒车≤%.2f，前进≤%.2f）' % (i, HARD_MAX_REVERSE_DUTY, HARD_MAX_DUTY))
        last_t = t
    return doc


class RouteLibrary:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def path_for(self, route_id):
        if not isinstance(route_id, str) or not _ID_RE.fullmatch(route_id):
            raise ValueError('无效路线 ID')
        return self.root / (route_id + '.json')

    def list(self, deleted=False):
        rows = []
        for path in sorted(self.root.glob('*.json')):
            try:
                doc = validate_route(json.loads(path.read_text(encoding='utf-8')))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if bool(doc.get('deleted_at')) != bool(deleted):
                continue
            rows.append(dict(id=doc['id'], name=doc['name'], samples=len(doc['samples']),
                             duration_s=doc['samples'][-1]['t'], created_at=doc.get('created_at'),
                             notes=doc.get('notes', ''), deleted_at=doc.get('deleted_at')))
        return rows

    def load(self, route_id):
        path = self.path_for(route_id)
        if not path.is_file():
            raise ValueError('路线不存在: ' + route_id)
        doc = validate_route(json.loads(path.read_text(encoding='utf-8')))
        if doc.get('deleted_at'):
            raise ValueError('路线已删除，请从回收站恢复')
        return doc

    def save(self, doc):
        doc = validate_route(doc)
        path = self.path_for(doc['id'])
        tmp = path.with_suffix('.json.tmp')
        payload = json.dumps(doc, ensure_ascii=False, indent=2) + '\n'
        with self.lock:
            tmp.write_text(payload, encoding='utf-8')
            tmp.replace(path)
        return doc['id']

    def set_deleted(self, route_id, deleted):
        with self.lock:
            path = self.path_for(route_id)
            if not path.is_file():
                raise ValueError('路线不存在: ' + route_id)
            doc = validate_route(json.loads(path.read_text(encoding='utf-8')))
            if deleted:
                doc.setdefault('deleted_at', now())
            else:
                doc.pop('deleted_at', None)
            self.save(doc)
            return dict(route_id=route_id, deleted=bool(deleted))


class RouteController:
    """Record samples from manual commands; play feeds Guard when hardware is on.

    When hardware_enabled is false, record/play run in dry_run: state machine and
    timeline only — no Guard.enable / serial motion.
    """

    def __init__(self, guard, library, clock=time.monotonic):
        self.guard = guard
        self.library = library
        self.clock = clock
        self.lock = threading.RLock()
        self.mode = 'idle'  # idle | recording | playing
        self.route_id = None
        self.error = ''
        self.dry_run = False
        self._samples = []
        self._record_name = ''
        self._record_started = None
        self._play_thread = None
        self._stop = threading.Event()
        self._watch_token = None
        self._last_watch = 0

    def status(self):
        with self.lock:
            return dict(mode=self.mode, route_id=self.route_id, error=self.error,
                        sample_count=len(self._samples), dry_run=self.dry_run,
                        hardware_enabled=bool(self.guard.cfg.get('hardware_enabled')),
                        monitor_required=self.mode=='playing' and not self.dry_run,
                        routes=self.library.list())

    def _require_idle(self):
        if self.mode != 'idle':
            raise ValueError('路线忙：当前为 ' + self.mode)

    def _hw(self):
        return bool(self.guard.cfg.get('hardware_enabled'))

    def set_deleted(self, route_id, deleted):
        with self.lock:
            self._require_idle()
            if self.guard.enabled or (self._play_thread and self._play_thread.is_alive()):
                raise ValueError('请先停止控制并结束路线，再管理路线')
            return self.library.set_deleted(route_id, deleted)

    def start_record(self, name=None):
        with self.lock:
            self._require_idle()
            self.dry_run = not self._hw()
            self.mode = 'recording'
            self.route_id = None
            self.error = ''
            self._samples = []
            self._record_name = (name or '现场录制').strip() or '现场录制'
            self._record_started = self.clock()
            return dict(mode=self.mode, dry_run=self.dry_run)

    def note_command(self, duty, steering):
        """Call after a successful manual Guard.command, or dry-run pad note."""
        with self.lock:
            if self.mode != 'recording' or self._record_started is None:
                return
            t = max(0.0, self.clock() - self._record_started)
            duty, steering = float(duty), float(steering)
            if not all(math.isfinite(v) for v in (t, duty, steering)):
                raise ValueError('录制指令必须为有限数值')
            duty = max(-HARD_MAX_REVERSE_DUTY, min(HARD_MAX_DUTY, duty))
            self._samples.append(dict(t=round(t, 3), duty=duty, steering=steering))

    def stop_record(self):
        with self.lock:
            if self.mode != 'recording':
                raise ValueError('当前未在录制')
            if len(self._samples) < 2:
                self.mode = 'idle'
                self.dry_run = False
                self._samples = []
                raise ValueError('样本过少，未保存')
            rid = 'route-' + uuid.uuid4().hex[:10]
            notes = '无硬件演练录制' if self.dry_run else '现场录制'
            doc = dict(schema=SCHEMA, id=rid, name=self._record_name, created_at=now(),
                       sample_hz=10, max_duty=HARD_MAX_DUTY, notes=notes,
                       samples=list(self._samples))
            self.library.save(doc)
            self.mode = 'idle'
            self.route_id = rid
            self.dry_run = False
            self._samples = []
            self._record_started = None
            return dict(route_id=rid, mode=self.mode)

    def play(self, route_id):
        with self.lock:
            self._require_idle()
            doc = self.library.load(route_id)
            self.dry_run = not self._hw()
            if not self.dry_run:
                if self.guard.enabled:
                    raise ValueError('已有手动控制会话，请先停止')
            self._stop.clear()
            self._watch_token = secrets.token_hex(16) if not self.dry_run else None
            self._last_watch = self.clock()
            self.mode = 'playing'
            self.route_id = doc['id']
            self.error = ''
            target = self._run_play_dry if self.dry_run else self._run_play
            self._play_thread = threading.Thread(target=target, args=(doc,), daemon=True)
            self._play_thread.start()
            return dict(mode=self.mode, route_id=self.route_id, dry_run=self.dry_run,
                        watch_token=self._watch_token)

    def watch(self, token):
        with self.lock:
            if self.mode != 'playing':
                return dict(active=False)
            if not isinstance(token, str) or not self._watch_token or not secrets.compare_digest(token,self._watch_token):
                raise ValueError('路线监护会话失效')
            self._last_watch = self.clock()
            return dict(active=True)

    def _run_play(self, doc):
        lease = None
        try:
            if not self.guard.transport_ok:
                raise ValueError('底盘反馈未就绪')
            lease = self.guard.enable()
            seq = 0
            t0 = self.clock()
            samples = doc['samples']
            i = 0
            last_duty, last_steering = 0.0, 0.0
            while not self._stop.is_set() and i < len(samples):
                with self.lock:
                    if self.clock()-self._last_watch > self.guard.cfg['heartbeat_timeout']:
                        raise ValueError('路线监护连接超时')
                elapsed = self.clock() - t0
                advanced = False
                while i < len(samples) and samples[i]['t'] <= elapsed:
                    sample = samples[i]
                    last_duty = float(sample['duty'])
                    last_steering = float(sample['steering'])
                    self.guard.command(dict(lease=lease, seq=seq,
                                            duty=last_duty, steering=last_steering))
                    seq += 1
                    i += 1
                    advanced = True
                if not advanced:
                    # Re-issue hold so sparse gaps do not trip heartbeat_timeout.
                    self.guard.command(dict(lease=lease, seq=seq,
                                            duty=last_duty, steering=last_steering))
                    seq += 1
                if not self.guard.enabled:
                    raise ValueError(self.guard.reason or '控制已锁定')
                time.sleep(0.05)
            self.guard.stop('路线回放结束')
        except Exception as e:
            self.error = str(e)
            self.guard.stop('路线回放中止: ' + str(e))
        finally:
            with self.lock:
                self.mode = 'idle'
                self.dry_run = False
                self._play_thread = None
                self._watch_token = None

    def _run_play_dry(self, doc):
        try:
            t0 = self.clock()
            duration = float(doc['samples'][-1]['t'])
            while not self._stop.is_set() and self.clock() - t0 < duration:
                time.sleep(0.05)
        except Exception as e:
            self.error = str(e)
        finally:
            with self.lock:
                self.mode = 'idle'
                self.dry_run = False
                self._play_thread = None

    def stop(self):
        with self.lock:
            if self.mode == 'recording':
                try:
                    return self.stop_record()
                except ValueError:
                    self.mode = 'idle'
                    self.dry_run = False
                    self._samples = []
                    if self._hw():
                        self.guard.stop('取消录制')
                    return dict(mode='idle', cancelled=True)
            if self.mode == 'playing':
                self._stop.set()
            if self._hw():
                self.guard.stop('路线停止')
            self.mode = 'idle'
            self.dry_run = False
            return dict(mode=self.mode)
