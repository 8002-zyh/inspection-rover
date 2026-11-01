import tempfile
import unittest
from unittest import mock
from patrol.common import configuration
from patrol.robot import Robot,make_app


class ReconnectTests(unittest.TestCase):
    def test_healthy_reconnect_is_noop_preserving_uart_and_feedback(self):
        with tempfile.TemporaryDirectory() as root:
            cfg=configuration();cfg['hardware_enabled']=True
            robot=Robot(cfg,{'device_token':'test'},root)
            robot.driver=mock.Mock(thread=None)
            robot.guard.transport_ok=True
            robot.guard.feedback_at=robot.guard.clock()
            robot.guard.feedback_rpm=0
            before=robot.guard.feedback_at
            with mock.patch('patrol.robot.SerialDriver') as factory:
                result=robot.reconnect_chassis()
                robot.driver.close.assert_not_called();factory.assert_not_called()
                self.assertTrue(result['already_connected'])
                self.assertTrue(result['connected']);self.assertFalse(result['started'])
                self.assertEqual(robot.guard.feedback_at,before)
                self.assertTrue(robot.guard.transport_ok);self.assertFalse(robot.guard.enabled)

    def test_reconnect_requires_idle_unarmed_and_never_enables(self):
        with tempfile.TemporaryDirectory() as root:
            cfg=configuration();cfg['hardware_enabled']=True
            robot=Robot(cfg,{'device_token':'test'},root)
            old=mock.Mock(thread=None);robot.driver=old
            robot.guard.transport_ok=True
            robot.guard.enable()
            with self.assertRaises(ValueError):robot.reconnect_chassis()
            old.close.assert_not_called()
            robot.guard.stop();robot.routes.mode='playing'
            with self.assertRaises(ValueError):robot.reconnect_chassis()
            old.close.assert_not_called()
            robot.routes.mode='idle';robot.guard.driver_error='write timeout'
            with mock.patch('patrol.robot.SerialDriver') as factory:
                response=robot.reconnect_chassis()
                old.close.assert_called_once()
                factory.return_value.start.assert_called_once()
                self.assertFalse(response['enabled']);self.assertFalse(robot.guard.enabled)
                self.assertFalse(robot.guard.transport_ok);self.assertEqual(robot.guard.driver_error,'')

    def test_reconnect_endpoint_auth_and_stuck_thread(self):
        with tempfile.TemporaryDirectory() as root:
            cfg=configuration();cfg['hardware_enabled']=True
            robot=Robot(cfg,{'device_token':'test'},root);robot.driver=mock.Mock()
            robot.driver.thread.is_alive.return_value=True
            c=make_app(robot).test_client()
            self.assertEqual(c.post('/control/reconnect',json={}).status_code,401)
            with mock.patch('patrol.robot.SerialDriver') as factory:
                r=c.post('/control/reconnect',json={},headers={'X-Device-Token':'test'})
                self.assertEqual(r.status_code,400);factory.assert_not_called()


if __name__=='__main__':unittest.main()
