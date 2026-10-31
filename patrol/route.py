"""Route file schema, library, and record/playback controller (no serial I/O)."""
import json
import re
import threading
import time
import uuid
from pathlib import Path

from .common import now
from .control import HARD_MAX_DUTY

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
        if t < last_t:
            raise ValueError('样本时间必须单调非降')
        if duty < 0 or duty > HARD_MAX_DUTY:
            raise ValueError('样本 #%d duty 非法（禁止倒车且≤%.2f）' % (i, HARD_MAX_DUTY))
        last_t = t
    return doc


class RouteLibrary:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, route_id):
        if not _ID_RE.fullmatch(route_id):
            raise ValueError('无效路线 ID')
        return self.root / (route_id + '.json')

    def list(self):
        rows = []
        for path in sorted(self.root.glob('*.json')):
            try:
                doc = validate_route(json.loads(path.read_text(encoding='utf-8')))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            rows.append(dict(id=doc['id'], name=doc['name'], samples=len(doc['samples']),
                             duration_s=doc['samples'][-1]['t'], created_at=doc.get('created_at'),
                             notes=doc.get('notes', '')))
        return rows

    def load(self, route_id):
        path = self.path_for(route_id)
        if not path.is_file():
            raise ValueError('路线不存在: ' + route_id)
        return validate_route(json.loads(path.read_text(encoding='utf-8')))

    def save(self, doc):
        doc = validate_route(doc)
        path = self.path_for(doc['id'])
        tmp = path.with_suffix('.json.tmp')
        payload = json.dumps(doc, ensure_ascii=False, indent=2) + '\n'
        tmp.write_text(payload, encoding='utf-8')
        tmp.replace(path)
        return doc['id']


class RouteController:
    """Record samples from manual commands; play feeds Guard when hardware is on."""

    def __init__(self, guard, library, clock=time.monotonic):
        self.guard = guard
        self.library = library
        self.clock = clock
        self.lock = threading.RLock()
        self.mode = 'idle'  # idle | recording | playing
        self.route_id = None
        self.error = ''
        self._samples = []
        self._record_name = ''
        self._record_started = None
        self._play_thread = None
        self._stop = threading.Event()

    def status(self):
        with self.lock:
            return dict(mode=self.mode, route_id=self.route_id, error=self.error,
                        sample_count=len(self._samples),
                        hardware_enabled=bool(self.guard.cfg.get('hardware_enabled')),
                        routes=self.library.list())

    def _require_idle(self):
        if self.mode != 'idle':
            raise ValueError('路线忙：当前为 ' + self.mode)

    def start_record(self, name=None):
        with self.lock:
            self._require_idle()
            if not self.guard.cfg.get('hardware_enabled'):
                raise ValueError('硬件未启用，拒绝录制（避免无实车动作的空路线）')
            self.mode = 'recording'
            self.route_id = None
            self.error = ''
            self._samples = []
            self._record_name = (name or '现场录制').strip() or '现场录制'
            self._record_started = self.clock()
            return dict(mode=self.mode)

    def note_command(self, duty, steering):
        """Call after a successful manual Guard.command while recording."""
        with self.lock:
            if self.mode != 'recording' or self._record_started is None:
                return
            t = max(0.0, self.clock() - self._record_started)
            duty = max(0.0, min(HARD_MAX_DUTY, float(duty)))
            self._samples.append(dict(t=round(t, 3), duty=duty, steering=float(steering)))

    def stop_record(self):
        with self.lock:
            if self.mode != 'recording':
                raise ValueError('当前未在录制')
            if len(self._samples) < 2:
                self.mode = 'idle'
                self._samples = []
                raise ValueError('样本过少，未保存')
            rid = 'route-' + uuid.uuid4().hex[:10]
            doc = dict(schema=SCHEMA, id=rid, name=self._record_name, created_at=now(),
                       sample_hz=10, max_duty=HARD_MAX_DUTY, notes='现场录制',
                       samples=list(self._samples))
            self.library.save(doc)
            self.mode = 'idle'
            self.route_id = rid
            self._samples = []
            self._record_started = None
            return dict(route_id=rid, mode=self.mode)

    def play(self, route_id):
        with self.lock:
            self._require_idle()
            if not self.guard.cfg.get('hardware_enabled'):
                raise ValueError('硬件未启用，拒绝路线回放')
            doc = self.library.load(route_id)
            if self.guard.enabled:
                raise ValueError('已有手动控制会话，请先停止')
            self._stop.clear()
            self.mode = 'playing'
            self.route_id = doc['id']
            self.error = ''
            self._play_thread = threading.Thread(target=self._run_play, args=(doc,), daemon=True)
            self._play_thread.start()
            return dict(mode=self.mode, route_id=self.route_id)

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
            while not self._stop.is_set() and i < len(samples):
                elapsed = self.clock() - t0
                while i < len(samples) and samples[i]['t'] <= elapsed:
                    sample = samples[i]
                    self.guard.command(dict(lease=lease, seq=seq,
                                            duty=sample['duty'], steering=sample['steering']))
                    seq += 1
                    i += 1
                if not self.guard.enabled:
                    raise ValueError(self.guard.reason or '控制已锁定')
                time.sleep(0.02)
            self.guard.stop('路线回放结束')
        except Exception as e:
            self.error = str(e)
            self.guard.stop('路线回放中止: ' + str(e))
        finally:
            with self.lock:
                self.mode = 'idle'
                self._play_thread = None

    def stop(self):
        with self.lock:
            if self.mode == 'recording':
                try:
                    return self.stop_record()
                except ValueError:
                    self.mode = 'idle'
                    self._samples = []
                    self.guard.stop('取消录制')
                    return dict(mode='idle', cancelled=True)
            if self.mode == 'playing':
                self._stop.set()
            self.guard.stop('路线停止')
            self.mode = 'idle'
            return dict(mode=self.mode)
