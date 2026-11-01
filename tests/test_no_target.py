import unittest
from patrol.common import configuration
from patrol.control import Guard

class NoTargetTests(unittest.TestCase):
    def guard(self, **overrides):
        cfg=configuration();cfg.update(hardware_enabled=True,front_sensor_id=0,front_no_target_policy='allow_supervised',stop_distance_m=.25)
        cfg.update(overrides)
        t=[10.0];g=Guard(cfg,lambda:t[0]);g.transport_ok=True
        return g,t

    def command(self,g):
        lease=g.enable();g.command(dict(lease=lease,seq=0,duty=.03,steering=0))

    def test_no_target_policy_requires_fresh_good_255(self):
        for code,good,age,allowed in ((255,True,0,True),(255,False,0,False),(7,True,0,False),(0,True,0,False),(255,True,.6,False)):
            with self.subTest(code=code,frame_ok=good,age=age):
                g,t=self.guard()
                g.ranges[0]=dict(at=t[0]-age,valid=False,frame_ok=good,sensor_status=code,distance=None)
                self.command(g)
                self.assertEqual(g.enabled,allowed)
                self.assertEqual(g.output()[0],.03 if allowed else 0)

    def test_near_obstacle_still_locks_and_does_not_restart(self):
        g,t=self.guard();g.ranges[0]=dict(at=t[0],valid=True,distance=.2,sensor_status=0,frame_ok=True)
        self.command(g);self.assertFalse(g.enabled)
        g.ranges[0]=dict(at=t[0],valid=False,distance=None,sensor_status=255,frame_ok=True)
        self.assertEqual(g.output()[0],0)

    def test_default_policy_stops_on_no_target(self):
        g,t=self.guard(front_no_target_policy='stop')
        g.ranges[0]=dict(at=t[0],valid=False,distance=None,sensor_status=255,frame_ok=True)
        self.command(g);self.assertFalse(g.enabled)

    def test_zero_strength_supervised_policy_and_timeout(self):
        g,t=self.guard()
        g.ranges[0]=dict(at=t[0],valid=False,distance=None,sensor_status=0,frame_ok=True,strength=0)
        self.command(g);self.assertTrue(g.enabled)
        t[0]+=.51;g.last=t[0]
        self.assertEqual(g.output()[0],0);self.assertEqual(g.reason,'前方测距失效')

    def test_phase_error_still_stops_even_when_strength_zero(self):
        g,t=self.guard()
        g.ranges[0]=dict(at=t[0],valid=False,distance=None,sensor_status=7,frame_ok=True,strength=0)
        self.command(g);self.assertFalse(g.enabled)
