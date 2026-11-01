import atexit
import io
import json
import os
import signal
import threading
import time
import uuid
from pathlib import Path
import requests
from flask import Flask, jsonify, request, Response
from .common import configuration, credentials, now
from .control import Guard, SerialDriver
from .route import RouteController, RouteLibrary
from .store import Store
from .vision import Vision, proximity_finding


class Robot:
    def __init__(self, cfg, secrets, root):
        self.cfg, self.secrets = cfg, secrets
        self.store = Store(root)
        self.guard = Guard(cfg)
        self.driver = SerialDriver(self.guard)
        routes_root = Path(root) / 'routes'
        example = Path(__file__).resolve().parent.parent / 'routes' / 'examples'
        self.routes = RouteController(self.guard, RouteLibrary(routes_root))
        # Seed library with committed examples if empty (read-only copy into runtime).
        if example.is_dir() and not any(routes_root.glob('*.json')):
            for src in example.glob('*.json'):
                try:
                    self.routes.library.save(json.loads(src.read_text(encoding='utf-8')))
                except (OSError, ValueError, json.JSONDecodeError):
                    pass
        self.vision = Vision(cfg)
        self.session = uuid.uuid4().hex
        self.checkpoint = None
        self.jpeg = None
        self.frame_at = None
        self.error = ''
        self.upload_error = ''
        self.last_upload = None
        self.quit = threading.Event()
        self.workers = []
        self.lock = threading.Lock()
        self.operator_lock = threading.RLock()
        self.capture_requested = False
        self.sampling = False
        self.range_error = '测距尚未启动'
        self.range_records = {}
        self.queue_bytes = None  # cached image bytes; computed once, then updated on save/cleanup

    def location(self):
        return dict(source='manual_checkpoint' if self.checkpoint else 'unavailable',
                    checkpoint=self.checkpoint, valid=bool(self.checkpoint),
                    frame_id=None, x=None, y=None, yaw=None)

    def reconnect_chassis(self):
        with self.operator_lock:
            if not self.cfg['hardware_enabled']:
                raise ValueError('当前仅监测模式，不能开启硬件写入')
            if self.guard.enabled or self.guard.duty!=0 or self.routes.mode!='idle':
                raise ValueError('请先停车并结束路线，再重连底盘')
            self.guard.stop('重连底盘')
            self.driver.close()
            if self.driver.thread and self.driver.thread.is_alive():
                raise ValueError('旧串口线程尚未退出，请现场重启小车')
            with self.guard.lock:
                self.guard.transport_ok=False
                self.guard.feedback_at=None
                self.guard.feedback_rpm=None
                self.guard.driver_error=''
            self.driver=SerialDriver(self.guard)
            self.driver.start()
            return dict(started=True,enabled=False)

    def status(self):
        return dict(device_id=self.cfg['device_id'], session_id=self.session,
                    frame_at=self.frame_at, camera_error=self.error,
                    inference_error=self.vision.error, model_loaded=self.vision.model is not None,
                    queue=self.store.counts(), upload_error=self.upload_error,
                    last_upload=self.last_upload, location=self.location(),
                    control=self.guard.status(), range_error=self.range_error,
                    ranges=self.range_records, sampling=self.sampling,
                    route=self.routes.status(),
                    route_mode=self.routes.mode, route_replay_available=True,
                    route_type='command_timeline', autonomous_available=False)

    def start(self):
        self.driver.start()
        for fn in (self.camera, self.uploader, self.measure):
            worker = threading.Thread(target=fn, daemon=True)
            self.workers.append(worker)
            worker.start()

    def camera(self):
        self.vision.load()
        while not self.quit.is_set():
            self.camera_connection()
            with self.lock:
                self.jpeg = None
                self.frame_at = None
            self.quit.wait(3)

    def camera_connection(self):
        pipeline = None
        try:
            import cv2
            import numpy as np
            import pyrealsense2 as rs
            pipeline = rs.pipeline()
            config = rs.config()
            config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 15)
            pipeline.start(config)
            last_sample = 0
            while not self.quit.is_set():
                frame = pipeline.wait_for_frames(3000).get_color_frame()
                if not frame:
                    continue
                image = np.asanyarray(frame.get_data())
                captured = now()
                ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ok:
                    continue
                jpeg = encoded.tobytes()
                with self.lock:
                    self.jpeg, self.frame_at = jpeg, captured
                    manual = self.capture_requested
                    self.capture_requested = False
                self.error = ''
                if time.monotonic()-last_sample < self.cfg['capture_interval'] and not manual:
                    continue
                last_sample = time.monotonic()
                if self.queue_bytes is None:
                    self.queue_bytes = sum(p.stat().st_size for p in self.store.images.glob('*') if p.is_file())
                if self.queue_bytes >= self.cfg['max_queue_bytes']:
                    self.error = '本地图片达到容量上限，停止保存；未删除证据'
                    continue
                location = self.location()
                findings = self.vision.detect(image)
                sid = self.cfg.get('front_sensor_id')
                with self.guard.lock:
                    reading = self.guard.ranges.get(sid)
                warning = proximity_finding(reading,
                    self.cfg.get('obstacle_event_distance_m', self.cfg['stop_distance_m']), sid)
                if warning:
                    findings.append(warning)
                for finding in findings:
                    event = self.vision.event(finding, location, self.session, captured)
                    if event and self.store.put(event, jpeg):
                        self.queue_bytes += len(jpeg)
                if manual or self.sampling or not self.vision.model:
                    category = 'manual_capture' if manual else 'pending_inference' if not self.vision.model else 'inspection_sample'
                    payload = dict(event_id=uuid.uuid4().hex, device_id=self.cfg['device_id'],
                                   captured_at=captured, category=category, confidence=None,
                                   location=location, session_id=self.session,
                                   model_version=self.vision.version,
                                   inference_state='pending' if not self.vision.model else 'identified')
                    if self.store.put(payload, jpeg):
                        self.queue_bytes += len(jpeg)
        except Exception as e:
            self.error = str(e)
        finally:
            if pipeline:
                try:
                    pipeline.stop()
                except Exception:
                    pass

    def uploader(self):
        delay = 1
        session = requests.Session()
        session.trust_env = False
        while not self.quit.is_set():
            rows = self.store.events(pending=True)
            if not rows:
                self.quit.wait(1)
                continue
            try:
                for row in rows:
                    image = row.pop('image')
                    row.pop('received_at', None)
                    row.pop('uploaded', None)
                    with (self.store.images / image).open('rb') as f:
                        result = session.post(self.cfg['server_url']+'/api/events',
                            headers={'X-Device-Token': self.secrets['device_token']},
                            data={'metadata': json.dumps(row, ensure_ascii=False)},
                            files={'image': ('capture.jpg', f, 'image/jpeg')}, timeout=(3, 12))
                    if 400 <= result.status_code < 500 and result.status_code not in (401, 429):
                        # Permanent rejection: mark failed so later events are not blocked.
                        self.store.fail(row['event_id'], '%d %s' % (result.status_code, result.text[:200]))
                        self.upload_error = '事件%s被服务端拒绝: %d' % (row['event_id'], result.status_code)
                        continue
                    result.raise_for_status()
                    if result.json().get('event_id') != row['event_id']:
                        raise ValueError('服务端未确认对应事件')
                    self.store.ack(row['event_id'])
                    self.last_upload = now()
                    if self.cfg.get('delete_uploaded_images', False):
                        target = self.store.images / image
                        size = target.stat().st_size if target.exists() else 0
                        target.unlink(missing_ok=True)
                        if self.queue_bytes is not None:
                            self.queue_bytes = max(0, self.queue_bytes - size)
                if not self.upload_error.startswith('事件'):
                    self.upload_error = ''
                delay = 1
            except Exception as e:
                self.upload_error = str(e)
                self.quit.wait(delay)
                delay = min(30, delay*2)

    def measure(self):
        while not self.quit.is_set():
            self.measure_connection()
            self.range_records = {sid: dict(r, valid=False) for sid, r in self.range_records.items()}
            with self.guard.lock:
                self.guard.ranges.clear()
            self.quit.wait(2)

    def measure_connection(self):
        port = None
        try:
            import serial
            port = serial.Serial(self.cfg['range_port'], self.cfg['range_baud'], timeout=0.08, write_timeout=0.2, exclusive=True)
            while not self.quit.is_set():
                records = {}
                front = self.cfg.get('front_sensor_id')
                others = [s for s in range(4) if s != front]
                # Front sensor between every other sensor: refresh period ~2 reads (<0.2s).
                order = [s for o in others for s in ((front, o) if front is not None else (o,))]
                for sid in order:
                    port.reset_input_buffer()
                    cmd = bytes([0x57, 0x10, 255, 255, sid, 255, 255])
                    port.write(cmd + bytes([sum(cmd)&255]))
                    data = port.read(16)
                    frame_ok = len(data)==16 and data[:2]==b'\x57\x00' and sum(data[:-1])&255==data[-1] and data[3]==sid
                    sensor_status = data[11] if frame_ok else None
                    distance = int.from_bytes(data[8:11], 'little', signed=False)/1000 if frame_ok else None
                    strength = int.from_bytes(data[12:14], 'little') if frame_ok else 0
                    valid = bool(frame_ok and strength > 0 and sensor_status==0 and distance > 0)
                    if not valid:
                        distance = None  # Do not present a retained/out-of-range distance as measured.
                    state = ('measured' if valid else 'no_target' if frame_ok and sensor_status==255
                             else 'no_echo' if frame_ok and sensor_status==0 and strength==0 else 'fault')
                    records[sid] = dict(distance=distance, strength=strength, valid=valid,
                                        frame_ok=frame_ok, sensor_status=sensor_status, state=state, captured_at=now())
                    with self.guard.lock:
                        self.guard.ranges[sid] = dict(records[sid], at=time.monotonic())
                self.range_records = records
                self.range_error = '' if any(r['valid'] for r in records.values()) else '无有效测距；传感器朝向尚需现场确认'
                self.quit.wait(0.02)
        except Exception as e:
            self.range_error = str(e)
        finally:
            if port:
                port.close()

    def close(self):
        self.quit.set()
        self.driver.close()
        for worker in self.workers:
            if worker is not threading.current_thread():
                worker.join(4)


def make_app(robot):
    app = Flask(__name__)
    @app.before_request
    def auth():
        import hmac
        if not hmac.compare_digest(request.headers.get('X-Device-Token', ''), robot.secrets['device_token']):
            return jsonify(error='Unauthorized'), 401

    @app.errorhandler(ValueError)
    def bad(e):
        return jsonify(error=str(e)), 400

    @app.get('/status')
    def status():
        return jsonify(robot.status())

    @app.get('/preview')
    def preview():
        with robot.lock:
            if not robot.jpeg:
                return jsonify(error='相机尚无画面'), 503
            return Response(robot.jpeg, mimetype='image/jpeg', headers={'Cache-Control': 'no-store'})

    @app.post('/control/<action>')
    def control(action):
        with robot.operator_lock:
            return control_action(action)

    def control_action(action):
        data = request.get_json(silent=True) or {}
        if action == 'stop':
            if robot.routes.mode != 'idle':
                robot.routes.stop()
            else:
                robot.guard.stop()
        elif action == 'enable':
            return jsonify(lease=robot.guard.enable())
        elif action == 'reconnect':
            return jsonify(robot.reconnect_chassis())
        elif action == 'heartbeat':
            robot.guard.command(data)
            robot.routes.note_command(robot.guard.duty, robot.guard.steering - robot.cfg['steering_center'])
        elif action == 'lights':
            # Independent of drive lease so night fill light can stay on while locked.
            robot.guard.set_lights(headlight=data.get('headlight'), hazard=data.get('hazard'))
        else:
            raise ValueError('未知操作')
        return jsonify(robot.guard.status())

    @app.post('/checkpoint')
    def checkpoint():
        value = (request.get_json() or {}).get('checkpoint')
        if value not in ('A', 'B', 'C', None):
            raise ValueError('检查点必须为A/B/C')
        robot.checkpoint = value
        return jsonify(robot.location())

    @app.post('/capture')
    def capture():
        if not robot.jpeg or robot.error:
            raise ValueError('相机未就绪')
        with robot.lock:
            robot.capture_requested = True
        return jsonify(accepted=True)

    @app.post('/sampling')
    def sampling():
        robot.sampling = bool((request.get_json() or {}).get('enabled'))
        return jsonify(enabled=robot.sampling)

    @app.get('/routes')
    def routes_list():
        return jsonify(robot.routes.library.list())

    @app.get('/routes/status')
    def routes_status():
        return jsonify(robot.routes.status())

    @app.post('/routes/record/start')
    def routes_record_start():
        name = (request.get_json(silent=True) or {}).get('name')
        return jsonify(robot.routes.start_record(name))

    @app.post('/routes/record/stop')
    def routes_record_stop():
        return jsonify(robot.routes.stop_record())

    @app.post('/routes/record/note')
    def routes_record_note():
        """Dry-run pad samples (no Guard lease). Also harmless during live record."""
        data = request.get_json(silent=True) or {}
        if robot.routes.mode != 'recording':
            raise ValueError('当前未在录制')
        try:
            duty = float(data.get('duty', 0))
            steering = float(data.get('steering', 0))
        except (TypeError, ValueError) as e:
            raise ValueError('duty/steering 无效') from e
        robot.routes.note_command(duty, steering)
        return jsonify(robot.routes.status())

    @app.post('/routes/play')
    def routes_play():
        rid = (request.get_json(silent=True) or {}).get('route_id')
        if not rid:
            raise ValueError('缺少 route_id')
        with robot.operator_lock:
            return jsonify(robot.routes.play(rid))

    @app.post('/routes/watch')
    def routes_watch():
        return jsonify(robot.routes.watch((request.get_json(silent=True) or {}).get('watch_token')))

    @app.post('/routes/stop')
    def routes_stop():
        return jsonify(robot.routes.stop())
    return app


if __name__ == '__main__':
    import fcntl
    Path('runtime').mkdir(exist_ok=True)
    instance_lock = open('runtime/robot.lock', 'a')
    try:
        fcntl.flock(instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('已有车端服务运行；请先停止旧实例')
    robot = Robot(configuration(), credentials(), os.environ.get('PATROL_DATA', 'runtime/robot'))
    atexit.register(robot.close)
    def shutdown(signum, frame):
        robot.close()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    robot.start()
    make_app(robot).run(host=robot.cfg.get('robot_bind_host', '127.0.0.1'), port=8766, threaded=True, debug=False, use_reloader=False)
