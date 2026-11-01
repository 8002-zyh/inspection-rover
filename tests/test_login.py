import tempfile
import unittest
from werkzeug.security import generate_password_hash
from patrol.common import configuration
from patrol.server import create_app

class LoginTests(unittest.TestCase):
    def test_session_saved_and_uncached_without_robot(self):
        with tempfile.TemporaryDirectory() as root:
            app=create_app(configuration(),dict(session_key='test',device_token='test',password_hash=generate_password_hash('test')),root)
            client=app.test_client()
            self.assertEqual(client.get('/api/session').status_code,401)
            self.assertEqual(client.post('/api/login',json={'username':'operator','password':'wrong'}).status_code,401)
            r=client.post('/api/login',json={'username':'operator','password':'test'})
            self.assertEqual(r.status_code,200)
            self.assertIn('HttpOnly',r.headers['Set-Cookie'])
            self.assertEqual(client.get('/api/session').json['csrf'],r.json['csrf'])
            for path in ('/','/api/session','/static/http.js'):
                result=client.get(path)
                self.assertEqual(result.status_code,200)
                self.assertEqual(result.headers['Cache-Control'],'no-store')
                result.close()
