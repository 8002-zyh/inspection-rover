"""Independent monotonic dead-man and bounded serial I/O. No vendor nodes started."""
import math
import logging
import secrets
import threading
import time


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
            seq = int(data['seq'])
            if seq <= self.seq:
                raise ValueError('过期控制指令')
            duty, steer = float(data['duty']), float(data['steering'])
            if not math.isfinite(duty) or not math.isfinite(steer):
                self.stop('无效控制数据')
                raise ValueError('控制值必须有限')
            self.seq, self.last = seq, self.clock()
            self.duty = max(-self.cfg['max_duty'], min(self.cfg['max_duty'], duty))
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
        try:
            import serial
            port = serial.Serial(self.guard.cfg['serial_port'], self.guard.cfg['serial_baud'], timeout=0, write_timeout=0.05, exclusive=True)
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
                        continue
                    last_feedback = time.monotonic()
                    self.guard.feedback_at = self.guard.clock()
                    rpm = int.from_bytes(buf[1:3], 'big')
                    self.guard.feedback_rpm = -rpm if buf[9] == 1 else rpm
                    del buf[:14]
                self.guard.transport_ok = bool(last_feedback and time.monotonic()-last_feedback < 0.5)
                if not self.guard.transport_ok:
                    self.guard.stop('底盘反馈缺失或过期')
                duty, steering = self.guard.output()
                if self.guard.cfg['hardware_enabled']:
                    port.write(packet(duty, steering))
                self.shutdown.wait(max(0, 0.01-(time.monotonic()-begin)))
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
                except Exception:
                    pass
                port.close()

    def close(self):
        self.guard.stop('关闭服务')
        self.shutdown.set()
        if self.thread:
            self.thread.join(1)
