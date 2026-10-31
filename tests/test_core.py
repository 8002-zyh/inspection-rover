import io
import json
import tempfile
import unittest
from PIL import Image
from werkzeug.security import generate_password_hash
from patrol.common import configuration
from unittest import mock
from patrol.control import Guard, packet, feedback_sane, HARD_MAX_DUTY
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
        self.assertEqual(g.output(),(.03,1620))
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

    def _guard(self):
        t=[10.0];cfg=configuration();cfg.update(hardware_enabled=True,front_sensor_id=0)
        g=Guard(cfg,lambda:t[0]);g.transport_ok=True;g.ranges[0]=dict(at=t[0],valid=True,distance=2.0)
        return g,t

    def test_negative_duty_clamped_to_zero(self):
        g,t=self._guard();l=g.enable();g.command(dict(lease=l,seq=0,duty=-.03,steering=0))
        self.assertEqual(g.output()[0],0.0)

    def test_hard_max_duty_ignores_config(self):
        g,t=self._guard();g.cfg['max_duty']=1;l=g.enable();g.command(dict(lease=l,seq=0,duty=1,steering=0))
        self.assertLessEqual(g.output()[0],HARD_MAX_DUTY);self.assertEqual(HARD_MAX_DUTY,.03)

    def test_bad_heartbeat_fields_rejected(self):
        g,t=self._guard()
        for bad in (dict(seq=0,duty=.01,steering=0),dict(lease='x',seq=0,duty=.01,steering=0)):
            with self.assertRaises(ValueError):g.command(bad)
            self.assertFalse(g.enabled)
        l=g.enable()
        for bad in (dict(lease=l,duty=.01,steering=0),dict(lease=l,seq='a',duty=.01,steering=0),dict(lease=l,seq=0,duty=None,steering=0)):
            with self.assertRaises(ValueError):g.command(bad)
        self.assertEqual(g.output()[0],0.0)

    def test_heartbeat_http_400(self):
        from patrol.robot import make_app
        g,t=self._guard()
        robot=mock.Mock();robot.guard=g;robot.secrets={'device_token':'tok'}
        c=make_app(robot).test_client()
        r=c.post('/control/heartbeat',json={'seq':0},headers={'X-Device-Token':'tok'})
        self.assertEqual(r.status_code,400);self.assertFalse(g.enabled)

    def test_cleared_ranges_stop(self):
        g,t=self._guard();l=g.enable();g.command(dict(lease=l,seq=0,duty=.03,steering=0))
        self.assertEqual(g.output()[0],.03)
        with g.lock:g.ranges.clear()
        self.assertEqual(g.output()[0],0.0);self.assertFalse(g.enabled)

    def test_feedback_frame_sanity(self):
        ok=bytes([255,0,0,5,220,0,0,0,0,0,0,0,0,254])
        self.assertTrue(feedback_sane(ok))
        self.assertFalse(feedback_sane(ok[:9]+bytes([7])+ok[10:]))
        self.assertFalse(feedback_sane(bytes([255,0xff,0xff])+ok[3:]))

    def test_upload_permanent_failure_does_not_block(self):
        from patrol.robot import Robot
        with tempfile.TemporaryDirectory() as root:
            cfg=configuration();robot=Robot(cfg,{'device_token':'t'},root)
            for i in range(2):
                robot.store.put(dict(event_id='queued-event-%04d'%i,device_id='car',captured_at='2026-10-29T00:00:0%dZ'%i,category='manual_capture',location={}),jpeg())
            calls=[]
            def post(url,**kw):
                eid=json.loads(kw['data']['metadata'])['event_id'];calls.append(eid)
                r=mock.Mock();r.status_code=400 if eid.endswith('0') else 200;r.text='bad'
                r.json.return_value={'event_id':eid};r.raise_for_status.return_value=None
                if len(calls)>=2:robot.quit.set()
                return r
            with mock.patch('patrol.robot.requests.Session') as S:
                S.return_value.post.side_effect=post;robot.uploader()
            self.assertEqual(calls,['queued-event-0000','queued-event-0001'])
            self.assertEqual(robot.store.events(True),[])
            self.assertEqual(robot.store.counts()['failed'],1)

if __name__=='__main__':unittest.main()
