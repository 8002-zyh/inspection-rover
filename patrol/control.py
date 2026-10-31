"""Independent monotonic dead-man and bounded serial I/O. No vendor nodes started."""
import math
import logging
import secrets
import threading
import time

HARD_MAX_DUTY = 0.07  # Absolute forward limit; config/env cannot raise it.
FEEDBACK_FRAMES_REQUIRED = 3  # Vendor 14-byte feedback has no checksum.


class Guard:
    def __init__(self, cfg, clock=time.monotonic):
        self.cfg, self.clock = cfg, clock
        self.lock = threading.RLock()
        self.enabled = False
        self.lease = None
        self.last = 0
        self.seq = -1
        self.duty = 0.0
        self.steering = cfg['steering_center']
        self.reason = '启动后未使能'
        self.transport_ok = False
        self.feedback_rpm = None
        self.feedback_at = None
        self.driver_error = ''
        self.ranges = {}

    def stop(self, reason='操作员停止'):
        with self.lock:
            self.enabled = False
            self.lease = None
            self.duty = 0.0
            self.steering = self.cfg['steering_center']
            self.reason = reason

    def enable(self):
        with self.lock:
            if not self.cfg['hardware_enabled'] or not self.transport_ok:
                raise ValueError('硬件控制未启用或底盘反馈未就绪')
            if self.enabled:
                raise ValueError('已有控制会话，请先停止')
            self.enabled = True
            self.lease = secrets.token_hex(16)
            self.last = self.clock()
            self.seq = -1
            self.reason = ''
            return self.lease

    def command(self, data):
        with self.lock:
            self.output()
            if not self.enabled or data.get('lease') != self.lease:
                raise ValueError('控制会话失效，请重新使能')
            try:
                seq = int(data['seq'])
                duty, steer = float(data['duty']), float(data['steering'])
            except (KeyError, TypeError, ValueError) as e:
                raise ValueError('控制字段缺失或类型错误') from e
            if seq <= self.seq:
                raise ValueError('过期控制指令')
            if not math.isfinite(duty) or not math.isfinite(steer):
                self.stop('无效控制数据')
                raise ValueError('控制值必须有限')
            self.seq, self.last = seq, self.clock()
            limit_duty = min(float(self.cfg['max_duty']), HARD_MAX_DUTY)
            self.duty = max(0.0, min(limit_duty, duty))  # No reverse: no rear range sensor.
            limit = self.cfg['steering_limit']
            self.steering = int(self.cfg['steering_center'] + max(-limit, min(limit, steer)))
            self.output()  # Apply obstacle guard before releasing the command lock.

    def output(self):
        with self.lock:
            if self.enabled and self.clock() - self.last > self.cfg['heartbeat_timeout']:
                self.stop('控制心跳超时')
            sid = self.cfg.get('front_sensor_id')
            if self.enabled and self.duty > 0 and sid is not None:
                reading = self.ranges.get(int(sid))
                if not reading or self.clock() - reading['at'] > 0.5 or not reading['valid']:
                    self.stop('前方测距失效')
                elif not isinstance(reading.get('distance'), (int, float)) or not math.isfinite(reading['distance']) or reading['distance'] <= 0:
                    self.stop('前方测距失效')
                elif reading['distance'] <= self.cfg['stop_distance_m']:
                    self.stop('前方障碍停车')
            return self.duty if self.enabled else 0.0, self.steering

    def status(self):
        duty, steering = self.output()
        with self.lock:
            age = None if self.feedback_at is None else max(0, self.clock()-self.feedback_at)
            return dict(enabled=self.enabled, hardware_enabled=self.cfg['hardware_enabled'],
                        transport_ok=self.transport_ok and age is not None and age < 0.5,
                        feedback_rpm=self.feedback_rpm if age is not None and age < 0.5 else None,
                        feedback_age_seconds=age, driver_error=self.driver_error, reason=self.reason, duty=duty,
                        steering=steering, mode='manual', obstacle_protection=self.cfg.get('front_sensor_id') is not None)


def packet(duty, steering):
    return (b'\xff' + bytes([int(duty < 0)]) + int(round(abs(duty)*100)).to_bytes(2, 'little') +
            int(steering).to_bytes(2, 'little') + b'\x00\x00\xfe')


def feedback_sane(frame):
    """Range checks from vendor parser (ROSPY_Orin_chasis_control); no checksum exists."""
    if len(frame) != 14 or frame[0] != 255 or frame[13] != 254:
        return False
    rpm = int.from_bytes(frame[1:3], 'big')
    return (rpm <= 5000 and frame[5] <= 2 and frame[6] <= 2
            and frame[7] <= 1 and frame[8] <= 1 and frame[9] <= 1 and frame[12] <= 1)


class SerialDriver:
    def __init__(self, guard):
        self.guard = guard
        self.shutdown = threading.Event()
        self.thread = None

    def start(self):
        if not self.guard.cfg['hardware_enabled'] and not self.guard.cfg.get('serial_monitor_only', False):
            return
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        port = None
        failure = None
        last_feedback = 0
        buf = bytearray()
        good_frames = 0
        try:
            import serial
            port = serial.Serial(self.guard.cfg['serial_port'], self.guard.cfg['serial_baud'], timeout=0, write_timeout=0.5, exclusive=True)
            while not self.shutdown.is_set():
                begin = time.monotonic()
                chunk = port.read(min(port.in_waiting, 256))
                buf.extend(chunk)
                while len(buf) >= 14:
                    if buf[0] != 255:
                        del buf[0]
                        continue
                    if buf[13] != 254:
                        del buf[0]
                        good_frames = 0
                        continue
                    if not feedback_sane(buf[:14]):
                        del buf[0]
                        good_frames = 0
                        continue
                    rpm = int.from_bytes(buf[1:3], 'big')
                    frame_sign = buf[9] == 1
                    del buf[:14]
                    good_frames = min(good_frames + 1, FEEDBACK_FRAMES_REQUIRED)
                    if good_frames >= FEEDBACK_FRAMES_REQUIRED:
                        last_feedback = time.monotonic()
                        with self.guard.lock:
                            self.guard.feedback_at = self.guard.clock()
                            self.guard.feedback_rpm = -rpm if frame_sign else rpm
                with self.guard.lock:
                    self.guard.transport_ok = bool(last_feedback and time.monotonic()-last_feedback < 0.5)
                    ok = self.guard.transport_ok
                if not ok:
                    good_frames = 0
                    self.guard.stop('底盘反馈缺失或过期')
                duty, steering = self.guard.output()
                if self.guard.cfg['hardware_enabled']:
                    port.write(packet(duty, steering))
                self.shutdown.wait(max(0, 0.002-(time.monotonic()-begin)))  # vendor: <400Hz abnormal; target ~500Hz
        except Exception as e:
            failure = type(e).__name__ + ': ' + str(e)
            self.guard.driver_error = failure
            logging.exception('Chassis serial driver failed')
            self.guard.stop('串口错误: ' + failure)
        finally:
            self.guard.transport_ok = False
            self.guard.stop('串口错误: ' + failure if failure else '控制驱动停止')
            if port:
                try:
                    if self.guard.cfg['hardware_enabled']:
                        port.write(packet(0.0, self.guard.cfg['steering_center']))
                except Exception as e:
                    self.guard.driver_error = ((failure + '; ') if failure else '') + '停车帧未送达: ' + type(e).__name__ + ': ' + str(e)
                    logging.error('Stop frame not delivered: %s', e)
                port.close()

    def close(self):
        self.guard.stop('关闭服务')
        self.shutdown.set()
        if self.thread:
            self.thread.join(1)
