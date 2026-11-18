"""Regressions for the recorded false hold, transient unknowns and hand distance."""
import unittest
from config import Config
from controller import Controller
from engine import Engine, Gesture
from gestures import Classifier
from synthetic import hand


class IntentTests(unittest.TestCase):
    def test_click_survives_brief_unknown_on_thumb_release(self):
        c=Controller(Config()); events=[]
        for t in range(0,900,20):
            g=(Gesture.OPEN if t<300 or t>=600 else
               Gesture.LEFT if t<520 else Gesture.OTHER)
            events+=c.update(hand(g),t)
        self.assertEqual(events,[('click','left')])

    def test_recorded_226ms_distance_cannot_press_button(self):
        e=Engine(); e.update(Gesture.OPEN,(0,0),0)
        e.update(Gesture.LEFT,(0,0),10)
        for t in (60,110,160,210,236):
            self.assertEqual(e.update(Gesture.LEFT,(.3,0),t),[])
        self.assertEqual(e.update(Gesture.OPEN,(.3,0),280),[('click','left')])

    def test_short_tap_with_large_motion_at_multiple_fps(self):
        for fps in (15,30,60,120):
            e=Engine(); events=[]
            for i in range(int(.6*fps)+1):
                t=i*1000/fps
                g=Gesture.OPEN if t<100 or t>=350 else Gesture.LEFT
                point=(.5 if t>=150 else 0.,0.)
                events+=e.update(g,point,t)
            self.assertEqual([x for x in events if x[0]!='move'],[('click','left')])

    def test_distance_requires_sustained_confirmation_after_tap_window(self):
        e=Engine(); e.update(Gesture.OPEN,(0,0),0); e.update(Gesture.LEFT,(0,0),10)
        for t in (110,210,310,410,470,530):
            self.assertEqual(e.update(Gesture.LEFT,(.3,0),t),[])
        events=e.update(Gesture.LEFT,(.3,0),580)
        self.assertEqual(events[0],('down','left'))
        self.assertEqual(e.activation,'deliberate_distance')


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.c=Controller(Config()); self.t=0; self.events=[]
        self.feed(Gesture.OPEN,300); self.feed(Gesture.LEFT,850)
        self.assertEqual(self.events,[('down','left')])

    def feed(self,g,duration):
        for _ in range(duration//20):
            self.events+=self.c.update(hand(g),self.t)
            self.t+=20

    def test_one_unknown_frame_freezes_then_resumes_without_release(self):
        self.feed(Gesture.OTHER,20)
        self.assertEqual(self.c.reason,'uncertain_frozen')
        self.assertEqual(self.events,[('down','left')])
        self.feed(Gesture.LEFT,100)
        self.assertEqual(self.c.engine.mode,'LEFT_DRAG')
        self.assertEqual(self.events,[('down','left')])
        self.feed(Gesture.OPEN,100)
        self.assertEqual(self.events,[('down','left'),('up','left')])

    def test_sustained_unknown_releases_exactly_once(self):
        self.feed(Gesture.OTHER,200)
        self.assertEqual(self.events,[('down','left'),('up','left')])
        self.feed(Gesture.LEFT,200)
        self.assertEqual(self.events,[('down','left'),('up','left')])

    def test_fist_during_grace_releases_immediately(self):
        self.feed(Gesture.OTHER,20); self.feed(Gesture.FIST,20)
        self.assertEqual(self.events,[('down','left'),('up','left')])

    def test_hand_loss_during_grace_releases_immediately(self):
        self.feed(Gesture.OTHER,20)
        self.events+=self.c.update(None,self.t)
        self.assertEqual(self.events,[('down','left'),('up','left')])

    def test_uncertainty_does_not_count_towards_hold_timer(self):
        c=Controller(Config()); events=[]
        for t in range(0,1040,20):
            g=Gesture.OPEN if t<300 else Gesture.LEFT
            # Three isolated unknowns interleaved with confirmed left frames.
            if t in (480,660,840): g=Gesture.OTHER
            events+=c.update(hand(g),t)
        self.assertNotIn(('down','left'),events)


class DistanceTests(unittest.TestCase):
    def test_same_physical_path_at_three_distances(self):
        paths=[]
        for scale in (.5,1.,1.8):
            c=Controller(Config()); events=[]
            for t in range(0,2400,20):
                x=max(0,t-300)*.00003*scale
                events+=c.update(hand(Gesture.OPEN,scale=scale,x=x),t)
            paths.append(sum(e[1] for e in events if e[0]=='move'))
        self.assertGreater(min(paths),0)
        self.assertLess(max(paths)/min(paths),1.01)

    def test_distant_tiny_hand_is_rejected(self):
        c=Controller(Config())
        self.assertEqual(c.update(hand(Gesture.OPEN,scale=.2),0),[])
        self.assertEqual(c.reason,'hand_too_far')

    def test_close_oversized_hand_is_rejected(self):
        c=Controller(Config())
        self.assertEqual(c.update(hand(Gesture.OPEN,scale=3.),0),[])
        self.assertEqual(c.reason,'hand_too_close')

    def test_palm_width_outlier_has_less_effect_on_motion_scale(self):
        original=hand(Gesture.OPEN)
        c=Classifier(); a=c.classify(original)
        original[5].x-=.03
        b=c.classify(original)
        self.assertLess(abs(a.tracking_scale-b.tracking_scale),abs(a.scale-b.scale))


if __name__=='__main__': unittest.main()
