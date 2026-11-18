import tempfile
from pathlib import Path
import unittest
from config import Config
from controller import Controller
from diagnostics import Diagnostics
from engine import Gesture
from synthetic import hand
from tools.replay_landmarks import replay


class ReplayTests(unittest.TestCase):
    def test_recorded_quick_cycle_replays_without_camera_or_os_events(self):
        cfg=Config(left_click_gesture='FIST')
        c=Controller(cfg)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sequence.jsonl'
            d=Diagnostics(path,record_landmarks=True)
            try:
                for t in range(0,800,20):
                    points=hand(Gesture.FIST if 300<=t<440 else Gesture.OPEN)
                    # Distort image depth/width so replay needs the recorded 3D pose.
                    image=hand(Gesture.FIST if 300<=t<440 else Gesture.OPEN)
                    for point in image:
                        point.x=.5+(point.x-.5)*.22
                    events=c.update(image,t,world_landmarks=points)
                    d.record(c,t,events,{},50,50,landmarks=image,world_landmarks=points)
            finally:d.close()
            result=replay(path,cfg)
            self.assertEqual(result['observed_events'],[('click','left')])
            self.assertEqual(result['observed_events'],result['replayed_events'])


if __name__=='__main__':unittest.main()
