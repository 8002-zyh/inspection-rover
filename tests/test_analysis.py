import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from PIL import Image
from werkzeug.security import generate_password_hash
from patrol.analysis import AnalysisService, AnalysisError, VisionAPI, validate_result
from patrol.store import Store
from patrol.server import create_app
from patrol.common import configuration

CFG=dict(api_key='test-key',base_url='https://example.invalid',model='test-model')
RESULT=dict(scene_summary='一只瓶子',assessment='uncertain',objects=['瓶子'],anomaly_type='unknown',
            evidence='未看清是否丢弃',recommendation='人工确认',limitations='单张照片')

def setup(store,eid='analysis-event-001'):
    b=io.BytesIO();Image.new('RGB',(32,24),'green').save(b,format='JPEG')
    store.put(dict(event_id=eid,device_id='test',captured_at='2026-11-01T00:00:00Z',category='manual_capture',location={'source':'unavailable'}),b.getvalue())
    return eid

class AnalysisTests(unittest.TestCase):
    def test_persistent_success_and_idempotence(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);eid=setup(store);a=AnalysisService(store,CFG)
            a.enqueue(eid);a.enqueue(eid)
            with mock.patch.object(a.client,'analyze',return_value=RESULT) as call:
                self.assertTrue(a.run_once());self.assertFalse(a.run_once());call.assert_called_once()
            self.assertEqual(a.enqueue(eid)['state'],'succeeded')
            self.assertEqual(AnalysisService(store,CFG).results()[eid]['result']['evidence'],RESULT['evidence'])

    def test_retry_does_not_lose_job_and_running_recovers(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);eid=setup(store);a=AnalysisService(store,CFG);a.enqueue(eid)
            with mock.patch.object(a.client,'analyze',side_effect=AnalysisError('offline',retry=True)):
                a.run_once()
            self.assertEqual(a.results()[eid]['state'],'pending')
            with store.connect() as c:
                c.execute("UPDATE analysis_jobs SET state='running'")
            b=AnalysisService(store,CFG);b.recover()
            self.assertEqual(b.results()[eid]['state'],'pending')
            with store.connect() as c:c.execute('UPDATE analysis_jobs SET next_at=0')
            with mock.patch.object(b.client,'analyze',return_value=RESULT):b.run_once()
            self.assertEqual(b.results()[eid]['state'],'succeeded')

    def test_terminal_failure_and_manual_retry(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);eid=setup(store);a=AnalysisService(store,CFG);a.enqueue(eid)
            with mock.patch.object(a.client,'analyze',side_effect=AnalysisError('HTTP 401')):a.run_once()
            self.assertEqual(a.results()[eid]['state'],'failed')
            a.enqueue(eid);self.assertEqual(a.results()[eid]['attempts'],0)

    def test_result_schema_and_review_required(self):
        self.assertTrue(validate_result(dict(RESULT,needs_review=False))['needs_review'])
        with self.assertRaises(AnalysisError):validate_result(dict(RESULT,assessment='drive_forward'))
        with self.assertRaises(AnalysisError):validate_result({'evidence':'incomplete'})

    def test_image_request_and_http_failures_hide_credentials(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);eid=setup(store);p=store.images/(eid+'.jpg');api=VisionAPI(CFG)
            r=mock.Mock(ok=True);r.json.return_value=dict(choices=[dict(finish_reason='stop',message=dict(content=json.dumps(RESULT)))],model='test')
            with mock.patch.object(api.http,'post',return_value=r) as call:
                result=api.analyze(p)
                body=call.call_args.kwargs['json']
                self.assertTrue(body['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,'))
                self.assertTrue(result['needs_review']);self.assertIn('source_image_sha256',result)
            r.ok=False;r.status_code=401
            with mock.patch.object(api.http,'post',return_value=r):
                with self.assertRaises(AnalysisError) as caught:api.analyze(p)
            self.assertNotIn('test-key',str(caught.exception));self.assertFalse(caught.exception.retry)

    def test_analysis_http_auth_and_persisted_result(self):
        with tempfile.TemporaryDirectory() as root:
            app=create_app(configuration(),dict(password_hash=generate_password_hash('pass'),session_key='test',device_token='token'),root)
            app.analysis=AnalysisService(app.store,CFG);eid=setup(app.store);c=app.test_client()
            self.assertEqual(c.post('/api/events/'+eid+'/analysis').status_code,401)
            csrf=c.post('/api/login',json={'username':'operator','password':'pass'}).json['csrf']
            self.assertEqual(c.post('/api/events/'+eid+'/analysis').status_code,403)
            self.assertEqual(c.post('/api/events/'+eid+'/analysis',headers={'X-CSRF-Token':csrf}).status_code,202)
            with mock.patch.object(app.analysis.client,'analyze',return_value=RESULT):app.analysis.run_once()
            self.assertEqual(c.get('/api/events').json[0]['analysis']['state'],'succeeded')
            self.assertNotIn('api_key',c.get('/api/analysis/status').json)
