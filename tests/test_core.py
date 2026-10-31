import io
import json
import tempfile
import unittest
from PIL import Image
from werkzeug.security import generate_password_hash
from patrol.common import configuration
from patrol.control import Guard, packet
from patrol.server import create_app
from patrol.store import Store


def jpeg():
    b=io.BytesIO();Image.new('RGB',(40,30),'green').save(b,format='JPEG');return b.getvalue()


class Tests(unittest.TestCase):
    def test_deadman_and_replay(self):
        t=[10.0];cfg=configuration();cfg['hardware_enabled']=True
        g=Guard(cfg,lambda:t[0]);g.transport_ok=True
        g.ranges[0]=dict(at=t[0],valid=True,distance=2.0)
        lease=g.enable();g.command(dict(lease=lease,seq=0,duty=1,steering=99999))
        self.assertEqual(g.output(),(.04,1620))
        with self.assertRaises(ValueError):g.command(dict(lease=lease,seq=0,duty=.03,steering=0))
        t[0]+=.501;self.assertEqual(g.output()[0],0);self.assertFalse(g.enabled)
        with self.assertRaises(ValueError):g.command(dict(lease=lease,seq=1,duty=.03,steering=0))

    def test_invalid_and_sensor_stop(self):
        cfg=configuration();cfg.update(hardware_enabled=True,front_sensor_id=0)
        g=Guard(cfg);g.transport_ok=True;l=g.enable()
        g.command(dict(lease=l,seq=0,duty=.03,steering=0));self.assertEqual(g.output()[0],0)
        self.assertFalse(g.enabled)
        l=g.enable()
        with self.assertRaises(ValueError):g.command(dict(lease=l,seq=0,duty=float('nan'),steering=0))
        self.assertFalse(g.enabled)

    def test_protocol_zero(self):
        self.assertEqual(packet(0.0,1500),b'\xff\x00\x00\x00\xdc\x05\x00\x00\xfe')

    def test_obstacle_rejects_before_output_and_requires_reenable(self):
        cfg=configuration();cfg.update(hardware_enabled=True,front_sensor_id=0)
        t=[10.0];g=Guard(cfg,lambda:t[0]);g.transport_ok=True
        for distance in (0.4,0.5,float('nan'),None):
            g.ranges[0]=dict(at=t[0],valid=True,distance=distance)
            lease=g.enable();g.command(dict(lease=lease,seq=0,duty=.03,steering=0))
            self.assertFalse(g.enabled);self.assertEqual(g.duty,0)
        g.ranges[0]=dict(at=t[0],valid=True,distance=1.0)
        self.assertFalse(g.enabled)
        lease=g.enable();g.command(dict(lease=lease,seq=0,duty=.03,steering=0))
        t[0]+=.51;g.last=t[0]
        self.assertEqual(g.output()[0],0)
        self.assertEqual(g.reason,'前方测距失效')

    def test_old_feedback_is_not_current_speed(self):
        t=[10.0];g=Guard(configuration(),lambda:t[0])
        g.transport_ok=True;g.feedback_at=10.0;g.feedback_rpm=0
        self.assertTrue(g.status()['transport_ok'])
        t[0]+=0.6
        self.assertIsNone(g.status()['feedback_rpm'])
        self.assertFalse(g.status()['transport_ok'])

    def test_persistence_idempotence_and_task(self):
        with tempfile.TemporaryDirectory() as root:
            s=Store(root);p=dict(event_id='test-event-0001',device_id='car',captured_at='2026-10-29T00:00:00+00:00',category='manual_capture',location={'source':'unavailable'})
            self.assertTrue(s.put(p,jpeg()));self.assertFalse(s.put(p,jpeg()))
            self.assertEqual(len(Store(root).events(True)),1)
            with self.assertRaises(ValueError):s.put(dict(p,category='other'),jpeg())
            tid=s.task_create(p['event_id']);self.assertEqual(tid,s.task_create(p['event_id']))
            with self.assertRaises(ValueError):s.transition(tid,'close')
            s.transition(tid,'claim')
            with self.assertRaises(ValueError):s.transition(tid,'submit','done')
            s.transition(tid,'submit','done',jpeg());s.transition(tid,'submit','done',jpeg())
            s.transition(tid,'return');s.transition(tid,'submit','again',jpeg());s.transition(tid,'close')
            self.assertEqual(s.tasks()[0]['state'],'closed');s.ack(p['event_id']);self.assertEqual(s.events(True),[])

    def test_auth_csrf_and_upload(self):
        with tempfile.TemporaryDirectory() as root:
            app=create_app(configuration(),dict(password_hash=generate_password_hash('pass'),session_key='test',device_token='token'),root)
            client=app.test_client()
            self.assertEqual(client.get('/api/events').status_code,401)
            self.assertEqual(client.post('/api/events').status_code,401)
            r=client.post('/api/login',json={'username':'operator','password':'pass'})
            csrf=r.json['csrf']
            self.assertEqual(client.post('/api/tasks',json={'event_id':'anything'}).status_code,403)
            self.assertEqual(client.post('/api/tasks',json={'event_id':'anything'},headers={'X-CSRF-Token':csrf}).status_code,400)
            self.assertEqual(client.get('/api/events').json,[])

    def test_http_task_roundtrip(self):
        with tempfile.TemporaryDirectory() as root:
            app=create_app(configuration(),dict(password_hash=generate_password_hash('pass'),session_key='test',device_token='token'),root)
            client=app.test_client()
            payload=dict(event_id='http-test-event',device_id='test',captured_at='2026-10-29T00:00:00Z',category='manual_capture',location={'source':'unavailable'})
            def upload(photo):
                return client.post('/api/events',headers={'X-Device-Token':'token'},data={'metadata':json.dumps(payload),'image':(io.BytesIO(photo),'sample.jpg')})
            self.assertEqual(upload(b'broken').status_code,400)
            self.assertEqual(client.get('/api/events').status_code,401)
            self.assertTrue(upload(jpeg()).json['created'])
            self.assertFalse(upload(jpeg()).json['created'])
            csrf=client.post('/api/login',json={'username':'operator','password':'pass'}).json['csrf']
            headers={'X-CSRF-Token':csrf}
            image_name=client.get('/api/events').json[0]['image']
            evidence=client.get('/images/'+image_name)
            self.assertEqual(evidence.status_code,200)
            self.assertEqual(evidence.data,jpeg())
            evidence.close()
            tid=client.post('/api/tasks',json={'event_id':payload['event_id']},headers=headers).json['task_id']
            base='/api/tasks/'+tid+'/'
            self.assertEqual(client.post(base+'claim',headers=headers).status_code,200)
            self.assertEqual(client.post(base+'submit',headers=headers,data={'note':'test'}).status_code,400)
            self.assertEqual(client.get('/api/tasks').json[0]['state'],'working')
            result=client.post(base+'submit',headers=headers,data={'note':'automated test only','photo':(io.BytesIO(jpeg()),'result.jpg')})
            self.assertEqual(result.status_code,200)
            self.assertEqual(client.get('/api/tasks').json[0]['state'],'review')
            self.assertEqual(client.post(base+'close',headers=headers).status_code,200)
            self.assertEqual(Store(root).tasks()[0]['state'],'closed')

if __name__=='__main__':unittest.main()
