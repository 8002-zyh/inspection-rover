import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from patrol.common import configuration
from patrol.control import Guard, HARD_MAX_DUTY
from patrol.route import RouteLibrary, RouteController, validate_route, SCHEMA
from patrol.robot import make_app, Robot


def sample_doc(**kw):
    doc = dict(schema=SCHEMA, id='demo-short-01', name='测试路线', created_at='2026-10-31T00:00:00+00:00',
               sample_hz=10, max_duty=0.03, notes='',
               samples=[{'t': 0.0, 'duty': 0.0, 'steering': 0},
                        {'t': 1.0, 'duty': 0.03, 'steering': -20},
                        {'t': 2.0, 'duty': 0.0, 'steering': 0}])
    doc.update(kw)
    return doc


class RouteTests(unittest.TestCase):
    def test_validate_rejects_reverse_and_over_duty(self):
        with self.assertRaises(ValueError):
            validate_route(sample_doc(samples=[{'t': 0, 'duty': -0.01, 'steering': 0},
                                               {'t': 1, 'duty': 0, 'steering': 0}]))
        with self.assertRaises(ValueError):
            validate_route(sample_doc(samples=[{'t': 0, 'duty': 0.04, 'steering': 0},
                                               {'t': 1, 'duty': 0, 'steering': 0}]))

    def test_library_roundtrip(self):
        with tempfile.TemporaryDirectory() as root:
            lib = RouteLibrary(root)
            lib.save(sample_doc())
            rows = lib.list()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['id'], 'demo-short-01')
            self.assertEqual(lib.load('demo-short-01')['name'], '测试路线')

    def test_record_and_play_reject_when_hardware_off(self):
        cfg = configuration()
        cfg['hardware_enabled'] = False
        with tempfile.TemporaryDirectory() as root:
            lib = RouteLibrary(root)
            lib.save(sample_doc())
            ctl = RouteController(Guard(cfg), lib)
            with self.assertRaises(ValueError) as e:
                ctl.start_record()
            self.assertIn('硬件未启用', str(e.exception))
            with self.assertRaises(ValueError) as e:
                ctl.play('demo-short-01')
            self.assertIn('硬件未启用', str(e.exception))
            st = ctl.status()
            self.assertEqual(st['mode'], 'idle')
            self.assertFalse(st['hardware_enabled'])
            self.assertEqual(len(st['routes']), 1)

    def test_record_saves_when_hardware_on(self):
        t = [10.0]
        cfg = configuration()
        cfg.update(hardware_enabled=True, front_sensor_id=None)
        g = Guard(cfg, lambda: t[0])
        g.transport_ok = True
        with tempfile.TemporaryDirectory() as root:
            lib = RouteLibrary(root)
            ctl = RouteController(g, lib, clock=lambda: t[0])
            ctl.start_record('单元测试')
            lease = g.enable()
            g.command(dict(lease=lease, seq=0, duty=0.03, steering=-10))
            ctl.note_command(g.duty, g.steering - cfg['steering_center'])
            t[0] += 0.5
            g.command(dict(lease=lease, seq=1, duty=0.0, steering=0))
            ctl.note_command(g.duty, g.steering - cfg['steering_center'])
            saved = ctl.stop_record()
            doc = lib.load(saved['route_id'])
            self.assertGreaterEqual(len(doc['samples']), 2)
            self.assertLessEqual(max(s['duty'] for s in doc['samples']), HARD_MAX_DUTY)

    def test_robot_http_rejects_play_when_hardware_off(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = configuration()
            cfg['hardware_enabled'] = False
            robot = Robot(cfg, {'device_token': 'tok'}, root)
            # ensure example or saved route exists
            robot.routes.library.save(sample_doc())
            c = make_app(robot).test_client()
            h = {'X-Device-Token': 'tok'}
            self.assertEqual(c.get('/routes', headers=h).status_code, 200)
            self.assertGreaterEqual(len(c.get('/routes', headers=h).json), 1)
            r = c.post('/routes/play', json={'route_id': 'demo-short-01'}, headers=h)
            self.assertEqual(r.status_code, 400)
            self.assertIn('硬件未启用', r.json['error'])
            r = c.post('/routes/record/start', json={}, headers=h)
            self.assertEqual(r.status_code, 400)


if __name__ == '__main__':
    unittest.main()
