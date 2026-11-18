import unittest
from config import Config
from controller import Controller
from engine import Gesture
from gestures import Classifier
from synthetic import hand


class FistPulseTests(unittest.TestCase):
    def run_path(self,pose,fps=30,duration=1100):
        c=Controller(Config(left_click_gesture='FIST')); events=[]
        for i in range(int(duration*fps/1000)+1):
            t=i*1000/fps
            events+=c.update(hand(pose(t)),t)
        return c,events

    def test_fast_close_open_cycle_at_different_frame_rates(self):
        for fps in (15,30,60,120):
            _,events=self.run_path(lambda t:Gesture.FIST if 300<=t<440 else Gesture.OPEN,fps)
            self.assertEqual(events,[('click','left')])

    def test_intermediate_shapes_and_late_thumb_do_not_lose_click(self):
        for fps in (15,30,60,120):
            def pose(t):
                if t<300 or t>=780:return Gesture.OPEN
                if t<380 or 520<=t<650:return Gesture.OTHER
                if t<520:return Gesture.FIST
                return Gesture.LEFT  # all four fingers open, thumb still folded
            _,events=self.run_path(pose,fps)
            self.assertEqual(events,[('click','left')])

    def test_one_closed_frame_is_noise_not_a_click(self):
        c=Controller(Config(left_click_gesture='FIST'));events=[]
        for t in range(0,700,20):
            events+=c.update(hand(Gesture.FIST if t==320 else Gesture.OPEN),t)
        self.assertEqual(events,[])

    def test_hold_never_emits_an_additional_single_click(self):
        _,events=self.run_path(lambda t:Gesture.FIST if 300<=t<1200 else Gesture.OPEN,duration=1500)
        self.assertEqual(events,[('down','left'),('up','left')])

    def test_loss_in_middle_of_cycle_never_clicks(self):
        c=Controller(Config(left_click_gesture='FIST'));events=[]
        for t in range(0,800,20):
            p=hand(Gesture.OPEN if t<300 or t>=500 else Gesture.FIST)
            events+=c.update(None if t==440 else p,t)
        self.assertEqual(events,[])

    def test_long_ambiguous_cycle_does_not_become_short_click(self):
        _,events=self.run_path(lambda t: Gesture.OPEN if t<300 or t>=950 else
            Gesture.OTHER if 380<=t<850 else Gesture.FIST,duration=1200)
        self.assertEqual(events,[])

    def test_laterally_resting_thumb_can_be_fist(self):
        p=hand(Gesture.FIST)
        p[4].x=.29; p[4].y=.57
        obs=Classifier().classify(p)
        self.assertGreater(obs.features['thumb_palm_distance'],.95)
        self.assertEqual(obs.gesture,Gesture.FIST)

    def test_collapsed_finger_cannot_be_retained_from_previous_fist(self):
        c=Classifier();c.classify(hand(Gesture.FIST))
        p=hand(Gesture.FIST)
        for i in (6,7,8):p[i].x,p[i].y,p[i].z=p[5].x,p[5].y,p[5].z
        self.assertEqual(c.classify(p).gesture,Gesture.OTHER)

    def test_one_uncertain_finger_retains_but_does_not_acquire_fist(self):
        p=hand(Gesture.FIST)
        p[7].y=.27;p[8].y=.30
        self.assertEqual(Classifier().classify(p).gesture,Gesture.OTHER)
        c=Classifier();c.classify(hand(Gesture.FIST))
        obs=c.classify(p)
        self.assertEqual(obs.gesture,Gesture.FIST)
        self.assertTrue(obs.features['fist_retained'])
        opened=hand(Gesture.OPEN);p[6:9]=opened[6:9]
        self.assertNotEqual(c.classify(p).gesture,Gesture.FIST)

    def test_curled_finger_just_outside_palm_radius_does_not_require_repositioning(self):
        from types import SimpleNamespace as P
        p=hand(Gesture.FIST)
        p[6:9]=[P(x=x,y=y,z=0.) for x,y in ((.36,.50),(.27,.55),(.22,.65))]
        obs=Classifier().classify(p)
        self.assertEqual(obs.features['fist_closed_fingers'],3)
        self.assertTrue(obs.features['fist_relaxed_entry'])
        self.assertEqual(obs.gesture,Gesture.FIST)


if __name__=='__main__':unittest.main()
