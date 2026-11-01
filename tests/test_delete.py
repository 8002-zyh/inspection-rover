import io
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image
from werkzeug.security import generate_password_hash
from patrol.analysis import AnalysisService
from patrol.common import configuration
from patrol.control import Guard
from patrol.robot import make_app
from patrol.route import SCHEMA, RouteLibrary, RouteController
from patrol.server import create_app
from patrol.store import Store


def photo():
    output = io.BytesIO()
    Image.new('RGB', (20, 20), 'blue').save(output, format='JPEG')
    return output.getvalue()


def event():
    return dict(event_id='delete-test-event', device_id='software-test', category='manual_capture',
                captured_at='2026-11-02T00:00:00Z', location={'source': 'unavailable'})


def route():
    return dict(schema=SCHEMA, id='delete-test-route', name='删除恢复测试（零动力）',
                samples=[dict(t=0, duty=0, steering=0), dict(t=1, duty=0, steering=0)])


class DeleteTests(unittest.TestCase):
    def test_event_trash_survives_restart_and_reupload_preserving_task_and_image(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root); store.put(event(), photo())
            tid = store.task_create(event()['event_id'])
            store.set_event_deleted(event()['event_id'], True)
            store.set_event_deleted(event()['event_id'], True)
            reopened = Store(root)
            self.assertEqual(reopened.events(), [])
            self.assertEqual(len(reopened.events(deleted=True)), 1)
            self.assertEqual(len(reopened.events(pending=True)), 1, 'Do not drop unuploaded evidence')
            self.assertNotIn('deleted_at', reopened.events(pending=True)[0])
            self.assertFalse(reopened.put(event(), photo()), 'Duplicate upload must not resurrect event')
            self.assertEqual(reopened.events(), [])
            self.assertEqual((reopened.images / reopened.tasks()[0]['image']).read_bytes(), photo())
            with self.assertRaises(ValueError): reopened.task_create(event()['event_id'])
            for action in ('claim', 'submit', 'close'):
                reopened.transition(tid, action, '软件测试', photo())
            self.assertEqual(reopened.tasks()[0]['state'], 'closed')
            reopened.set_event_deleted(event()['event_id'], False)
            reopened.set_event_deleted(event()['event_id'], False)
            self.assertEqual(reopened.task_create(event()['event_id']), tid)
            self.assertEqual(len(reopened.events()), 1)
            self.assertEqual(reopened.events(deleted=True), [])

    def test_existing_database_gets_additive_trash_table_without_losing_data(self):
        with tempfile.TemporaryDirectory() as root:
            db = sqlite3.connect(str(Path(root) / 'patrol.sqlite3'))
            db.execute('CREATE TABLE events(id TEXT PRIMARY KEY,payload TEXT,image TEXT,digest TEXT,received TEXT,uploaded INTEGER DEFAULT 0,attempts INTEGER DEFAULT 0)')
            db.execute('INSERT INTO events(id,payload,image,digest,received) VALUES(?,?,?,?,?)',
                       (event()['event_id'], json.dumps(event()), 'existing.jpg', 'unchanged', '2026-11-02'))
            db.commit(); db.close()
            store = Store(root)
            self.assertEqual(store.events()[0]['image'], 'existing.jpg')
            store.set_event_deleted(event()['event_id'], True)
            store.set_event_deleted(event()['event_id'], False)
            with store.connect() as db:
                self.assertEqual(db.execute('SELECT digest FROM events').fetchone()[0], 'unchanged')

    def test_http_delete_restore_requires_login_csrf_and_keeps_image_access(self):
        with tempfile.TemporaryDirectory() as root:
            app = create_app(configuration(), dict(session_key='test', device_token='test',
                             password_hash=generate_password_hash('test')), root)
            app.store.put(event(), photo())
            client = app.test_client(); url = '/api/events/' + event()['event_id']
            self.assertEqual(client.post(url + '/delete').status_code, 401)
            csrf = client.post('/api/login', json=dict(username='operator', password='test')).json['csrf']
            self.assertEqual(client.post(url + '/delete').status_code, 403)
            headers = {'X-CSRF-Token': csrf}
            self.assertEqual(client.post(url + '/delete', headers=headers).status_code, 200)
            self.assertEqual(client.get('/api/events').json, [])
            row = client.get('/api/events?deleted=1').json[0]
            image = client.get('/images/' + row['image'])
            self.assertEqual(image.status_code, 200); image.close()
            self.assertEqual(client.post(url + '/restore', headers=headers).status_code, 200)
            self.assertEqual(len(client.get('/api/events').json), 1)
            self.assertEqual(client.post('/api/events/missing-item/delete', headers=headers).status_code, 400)

    def test_trashed_queued_analysis_pauses_until_restore(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root); store.put(event(), photo())
            service = AnalysisService(store, dict(api_key='test', model='test', base_url='http://unused'))
            service.client = mock.Mock(); service.client.analyze.return_value = {'assessment': 'uncertain'}
            service.enqueue(event()['event_id']); store.set_event_deleted(event()['event_id'], True)
            with self.assertRaises(ValueError): service.enqueue(event()['event_id'])
            self.assertFalse(service.run_once()); service.client.analyze.assert_not_called()
            store.set_event_deleted(event()['event_id'], False)
            self.assertTrue(service.run_once()); service.client.analyze.assert_called_once()

    def test_route_delete_restore_preserves_samples_and_refuses_deleted_play(self):
        with tempfile.TemporaryDirectory() as root:
            lib = RouteLibrary(root); lib.save(route())
            lib.set_deleted(route()['id'], True); lib.set_deleted(route()['id'], True)
            lib = RouteLibrary(root)
            self.assertEqual(lib.list(), [])
            self.assertEqual(len(lib.list(deleted=True)), 1)
            guard = Guard(configuration()); controller = RouteController(guard, lib)
            with mock.patch.object(guard, 'enable') as enable:
                with self.assertRaises(ValueError): controller.play(route()['id'])
                enable.assert_not_called()
            lib.set_deleted(route()['id'], False); lib.set_deleted(route()['id'], False)
            self.assertEqual(lib.load(route()['id'])['samples'], route()['samples'])
            self.assertEqual(lib.list(deleted=True), [])
            for bad in (None, '', '../elsewhere', '/absolute', 'bad/id'):
                with self.subTest(route_id=bad), self.assertRaises(ValueError): lib.set_deleted(bad, True)

    def test_busy_or_enabled_controller_cannot_delete_or_restore(self):
        with tempfile.TemporaryDirectory() as root:
            lib = RouteLibrary(root); lib.save(route())
            guard = Guard(configuration()); controller = RouteController(guard, lib)
            for mode, enabled in (('recording', False), ('playing', False), ('idle', True)):
                controller.mode = mode; guard.enabled = enabled
                for deleted in (True, False):
                    with self.subTest(mode=mode, deleted=deleted), self.assertRaises(ValueError):
                        controller.set_deleted(route()['id'], deleted)
                self.assertEqual(len(lib.list()), 1)

    def test_robot_route_management_auth_and_invalid_id(self):
        with tempfile.TemporaryDirectory() as root:
            guard = Guard(configuration()); lib = RouteLibrary(root); lib.save(route())
            bot = SimpleNamespace(guard=guard, routes=RouteController(guard, lib),
                                  operator_lock=threading.RLock(), secrets={'device_token': 'test'})
            client = make_app(bot).test_client(); headers = {'X-Device-Token': 'test'}
            self.assertEqual(client.post('/routes/delete', json={'route_id': route()['id']}).status_code, 401)
            self.assertEqual(client.post('/routes/delete', json={}, headers=headers).status_code, 400)
            self.assertEqual(client.post('/routes/delete', json={'route_id': route()['id']}, headers=headers).status_code, 200)
            self.assertEqual(len(client.get('/routes/trash', headers=headers).json), 1)
            self.assertEqual(client.post('/routes/restore', json={'route_id': route()['id']}, headers=headers).status_code, 200)

    def test_workbench_proxy_allows_only_management_methods(self):
        with tempfile.TemporaryDirectory() as root:
            app = create_app(configuration(), dict(session_key='test', device_token='test',
                             password_hash=generate_password_hash('test')), root)
            client = app.test_client()
            csrf = client.post('/api/login', json=dict(username='operator', password='test')).json['csrf']
            response = mock.Mock(content=b'{}', status_code=200, headers={'Content-Type': 'application/json'})
            with mock.patch('requests.Session.request', return_value=response) as request:
                for action in ('delete', 'restore'):
                    self.assertEqual(client.post('/api/robot/routes/' + action, json={'route_id': route()['id']},
                                                 headers={'X-CSRF-Token': csrf}).status_code, 200)
                self.assertEqual(client.get('/api/robot/routes/trash').status_code, 200)
                self.assertEqual(request.call_count, 3)
                self.assertEqual(client.get('/api/robot/routes/delete').status_code, 404)
