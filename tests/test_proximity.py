import unittest
from patrol.common import configuration
from patrol.control import Guard
from patrol.vision import proximity_finding


class ProximityTests(unittest.TestCase):
    def test_evidence_precedes_stop_but_does_not_change_stop_threshold(self):
        cfg=configuration();cfg.update(hardware_enabled=True,front_sensor_id=0,
                                       stop_distance_m=.25,obstacle_event_distance_m=.8)
        guard=Guard(cfg,lambda:10.0);guard.transport_ok=True
        for distance,expected_enabled in ((.329,True),(.25,False),(.20,False)):
            with self.subTest(distance=distance):
                guard.stop();reading=dict(valid=True,distance=distance,at=10.0,
                                          frame_ok=True,sensor_status=0,strength=21)
                guard.ranges[0]=reading
                event=proximity_finding(reading,.8,0,10.0)
                self.assertEqual(event['distance_m'],distance)
                self.assertEqual(event['distance_reference'],'front_sensor')
                lease=guard.enable()
                guard.command(dict(lease=lease,seq=0,duty=.03,steering=0))
                self.assertEqual(guard.enabled,expected_enabled)
                self.assertEqual(guard.output()[0],.03 if expected_enabled else 0)

    def test_invalid_stale_out_of_range_not_published_as_obstacle(self):
        for reading in (None,dict(valid=False),dict(valid=True,distance=None,at=10),
                        dict(valid=True,distance=float('nan'),at=10),
                        dict(valid=True,distance=-.2,at=10),
                        dict(valid=True,distance=.9,at=10),
                        dict(valid=True,distance=.3,at=9.49),
                        dict(valid=True,distance=.3,at=11)):
            with self.subTest(reading=reading):
                self.assertIsNone(proximity_finding(reading,.8,0,10))


if __name__=='__main__':unittest.main()
