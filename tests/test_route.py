import json
import tempfile
import threading
import time
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
            validate_route(sample_doc(samples=[{'t': 0, 'duty': HARD_MAX_DUTY + 0.01, 'steering': 0},
                                               {'t': 1, 'duty': 0, 'steering': 0}]))

    def test_library_roundtrip(self):
        with tempfile.TemporaryDirectory() as root:
            lib = RouteLibrary(root)
            lib.save(sample_doc())
            rows = lib.list()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['id'], 'demo-short-01')
            self.assertEqual(lib.load('demo-short-01')['name'], '测试路线')

    def test_record_and_play_dry_run_when_hardware_off(self):
        cfg = configuration()
        cfg['hardware_enabled'] = False
        with tempfile.TemporaryDirectory() as root:
            lib = RouteLibrary(root)
            lib.save(sample_doc())
            t = [100.0]
            ctl = RouteController(Guard(cfg), lib, clock=lambda: t[0])
            started = ctl.start_record('演练')
            self.assertEqual(started['mode'], 'recording')
            self.assertTrue(started['dry_run'])
            ctl.note_command(0.03, -15)
            t[0] += 0.2
            ctl.note_command(0.03, 0)
            saved = ctl.stop_record()
            self.assertIn('route_id', saved)
            st = ctl.status()
            self.assertEqual(st['mode'], 'idle')
            self.assertFalse(st['hardware_enabled'])

            played = ctl.play(saved['route_id'])
            self.assertEqual(played['mode'], 'playing')
            self.assertTrue(played['dry_run'])
            # Advance fake clock past duration while play thread uses real sleep —
            # stop explicitly for deterministic unit test.
            ctl.stop()
            self.assertEqual(ctl.status()['mode'], 'idle')

    def test_record_saves_when_hardware_on(self):
        t = [10.0]
        cfg = configuration()
        cfg.update(hardware_enabled=True, front_sensor_id=None)
        g = Guard(cfg, lambda: t[0])
        g.transport_ok = True
        with tempfile.TemporaryDirectory() as root:
            lib = RouteLibrary(root)
            ctl = RouteController(g, lib, clock=lambda: t[0])
            started = ctl.start_record('单元测试')
            self.assertFalse(started['dry_run'])
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

    def test_play_holds_heartbeat_across_sparse_samples(self):
        cfg = configuration()
        cfg.update(hardware_enabled=True, front_sensor_id=None, heartbeat_timeout=0.5)
        g = Guard(cfg)
        g.transport_ok = True
        with tempfile.TemporaryDirectory() as root:
            lib = RouteLibrary(root)
            # Gaps > heartbeat_timeout would lock without hold re-issue.
            lib.save(sample_doc(samples=[
                {'t': 0.0, 'duty': 0.03, 'steering': 0},
                {'t': 1.2, 'duty': 0.03, 'steering': -20},
                {'t': 1.35, 'duty': 0.0, 'steering': 0},
            ]))
            ctl = RouteController(g, lib)
            ctl.play('demo-short-01')
            deadline = time.monotonic() + 4.0
            while time.monotonic() < deadline and ctl.status()['mode'] != 'idle':
                time.sleep(0.05)
            st = ctl.status()
            self.assertEqual(st['mode'], 'idle', st)
            self.assertEqual(st['error'], '', st)

    def test_robot_http_dry_run_and_note(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = configuration()
            cfg['hardware_enabled'] = False
            robot = Robot(cfg, {'device_token': 'tok'}, root)
            robot.routes.library.save(sample_doc())
            c = make_app(robot).test_client()
            h = {'X-Device-Token': 'tok'}
            self.assertEqual(c.get('/routes', headers=h).status_code, 200)
            r = c.post('/routes/record/start', json={'name': 'http演练'}, headers=h)
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json['dry_run'])
            self.assertEqual(r.json['mode'], 'recording')
            r = c.post('/routes/record/note', json={'duty': 0.03, 'steering': -10}, headers=h)
            self.assertEqual(r.status_code, 200)
            r = c.post('/routes/record/note', json={'duty': 0.0, 'steering': 0}, headers=h)
            self.assertEqual(r.status_code, 200)
            r = c.post('/routes/record/stop', json={}, headers=h)
            self.assertEqual(r.status_code, 200)
            rid = r.json['route_id']
            r = c.post('/routes/play', json={'route_id': rid}, headers=h)
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json['dry_run'])
            c.post('/routes/stop', json={}, headers=h)
            st = c.get('/routes/status', headers=h).json
            self.assertEqual(st['mode'], 'idle')

    def test_robot_http_live_play_rejects_without_transport(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = configuration()
            cfg.update(hardware_enabled=True, front_sensor_id=None)
            robot = Robot(cfg, {'device_token': 'tok'}, root)
            robot.routes.library.save(sample_doc())
            # transport_ok stays false → play thread sets error, returns to idle
            c = make_app(robot).test_client()
            h = {'X-Device-Token': 'tok'}
            r = c.post('/routes/play', json={'route_id': 'demo-short-01'}, headers=h)
            self.assertEqual(r.status_code, 200)
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                st = c.get('/routes/status', headers=h).json
                if st['mode'] == 'idle':
                    break
                time.sleep(0.05)
            st = c.get('/routes/status', headers=h).json
            self.assertEqual(st['mode'], 'idle')
            self.assertIn('底盘反馈', st.get('error', ''))


if __name__ == '__main__':
    unittest.main()
