import unittest
from patrol.common import configuration
from patrol.control import Guard

class StopEvidenceTests(unittest.TestCase):
    def guard(self):
        cfg=configuration();cfg.update(hardware_enabled=True,front_sensor_id=0,stop_distance_m=.25)
        t=[10.0];g=Guard(cfg,lambda:t[0]);g.transport_ok=True
        return g,t

    def test_trigger_frame_is_preserved_after_reading_recovers(self):
        g,t=self.guard()
        reading=dict(at=10.0,valid=False,frame_ok=True,sensor_status=7,strength=1,distance=None)
        g.ranges[0]=reading
        lease=g.enable();g.command(dict(lease=lease,seq=0,duty=.03,steering=0))
        evidence=g.status()['last_stop']
        self.assertEqual(evidence['reason'],'前方测距失效')
        self.assertEqual(evidence['front']['sensor_status'],7)
        reading['sensor_status']=0
        g.ranges[0]=dict(at=10.0,valid=True,distance=.41)
        g.stop('操作员停止')
        self.assertEqual(g.status()['last_stop'],evidence)
        self.assertFalse(g.enabled)

    def test_near_obstacle_and_timeout_have_distinct_evidence(self):
        for distance,age,reason in ((.2,0,'前方障碍停车'),(.4,.6,'前方测距失效')):
            g,t=self.guard();g.ranges[0]=dict(at=10.0-age,valid=True,distance=distance)
            lease=g.enable();g.command(dict(lease=lease,seq=0,duty=.03,steering=0))
            self.assertEqual(g.status()['last_stop']['reason'],reason)
            self.assertAlmostEqual(g.status()['last_stop']['front']['age_seconds'],age)
