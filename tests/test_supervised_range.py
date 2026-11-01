"""Supervised range policy regression; fake clock/serial, no hardware movement."""
import unittest
from unittest import mock

from patrol.common import configuration
from patrol.control import Guard, SerialDriver


class SupervisedRangeTests(unittest.TestCase):
    def guard(self):
        cfg = configuration()
        cfg.update(hardware_enabled=True, front_sensor_id=0, stop_distance_m=.25,
                   front_range_failure_policy='allow_supervised')
        clock = [10.0]
        guard = Guard(cfg, lambda: clock[0])
        guard.transport_ok = True
        return guard, clock

    def drive(self, guard):
        lease = guard.enable()
        guard.command(dict(lease=lease, seq=0, duty=.03, steering=0))

    def test_missing_invalid_and_stale_ranges_do_not_interrupt_supervised_drive(self):
        cases = {
            'missing': None,
            'phase_error': dict(valid=False, sensor_status=7, strength=3, distance=None),
            'no_target': dict(valid=False, sensor_status=255, distance=None),
            'no_echo': dict(valid=False, sensor_status=0, strength=0, distance=None),
            'bad_frame': dict(valid=False, frame_ok=False, distance=None),
            'bad_frame_with_distance': dict(valid=True, frame_ok=False, distance=.1),
            'stale_near': dict(valid=True, distance=.1, at=9.4),
            'future_stamp': dict(valid=True, distance=.1, at=11),
            'nan': dict(valid=True, distance=float('nan')),
            'infinity': dict(valid=True, distance=float('inf')),
            'null': dict(valid=True, distance=None),
            'zero': dict(valid=True, distance=0),
            'negative': dict(valid=True, distance=-1),
        }
        for name, fields in cases.items():
            with self.subTest(name=name):
                guard, clock = self.guard()
                if fields is not None:
                    guard.ranges[0] = dict(at=clock[0], frame_ok=True)
                    guard.ranges[0].update(fields)
                self.drive(guard)
                self.assertTrue(guard.enabled)
                self.assertEqual(guard.output()[0], .03)
                status = guard.status()
                self.assertFalse(status['front_range_valid'])
                self.assertIsNone(status['front_distance_m'])
                self.assertIsNone(status['last_stop'])
                # Clear/disconnected range source must not silently revoke control.
                guard.ranges.clear()
                self.assertEqual(guard.output()[0], .03)

    def test_valid_obstacle_still_stops_and_clear_path_does_not_auto_resume(self):
        for distance in (.2, .25):
            with self.subTest(distance=distance):
                guard, clock = self.guard()
                self.drive(guard)  # Starts with no range, as explicitly authorized.
                guard.ranges[0] = dict(at=clock[0], valid=True, frame_ok=True,
                                       sensor_status=0, strength=3, distance=distance)
                self.assertEqual(guard.output()[0], 0)
                self.assertFalse(guard.enabled)
                self.assertEqual(guard.reason, '前方障碍停车')
                guard.ranges[0]['distance'] = 1
                self.assertEqual(guard.output()[0], 0)

    def test_valid_far_range_and_heartbeat_timeout(self):
        guard, clock = self.guard()
        guard.ranges[0] = dict(at=clock[0], valid=True, distance=.251)
        self.drive(guard)
        self.assertTrue(guard.status()['front_range_valid'])
        self.assertEqual(guard.status()['front_distance_m'], .251)
        clock[0] += .501
        self.assertEqual(guard.output()[0], 0)
        self.assertEqual(guard.reason, '控制心跳超时')

    def test_default_code_policy_remains_strict(self):
        guard, clock = self.guard()
        del guard.cfg['front_range_failure_policy']
        self.drive(guard)
        self.assertFalse(guard.enabled)
        self.assertEqual(guard.reason, '前方测距失效')

    def test_chassis_feedback_loss_still_stops_with_supervised_range(self):
        guard, clock = self.guard()
        self.drive(guard)
        driver = SerialDriver(guard)
        port = mock.Mock(in_waiting=0)
        port.read.return_value = b''
        with mock.patch.dict('sys.modules', {'serial': mock.Mock(Serial=mock.Mock(return_value=port))}), \
                mock.patch.object(driver.shutdown, 'wait', side_effect=lambda _: driver.shutdown.set()):
            driver.run()
        self.assertFalse(guard.enabled)
        self.assertEqual(guard.last_stop['reason'], '底盘反馈缺失或过期')
        self.assertTrue(all(call.args[0][1:4] == b'\x00\x00\x00'
                            for call in port.write.call_args_list))
