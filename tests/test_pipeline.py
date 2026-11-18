import math
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from config import Config
from engine import Gesture
from controller import Controller
from gestures import Classifier
from motion import PalmTracker, RelativeMotion
from synthetic import hand


class GeometryTests(unittest.TestCase):
    def test_world_pose_survives_foreshortened_image(self):
        aspect = 4 / 3
        for gesture in Gesture:
            for yaw in (-75, -40, 40, 75):
                for size in (.38, 1.):
                    pose = hand(gesture, scale=.2, mirror=yaw < 0)
                    tilt = math.radians(yaw)
                    world = [SimpleNamespace(x=(v.x-.5)*math.cos(tilt), y=v.y-.6,
                                             z=(v.x-.5)*math.sin(tilt)) for v in pose]
                    image = [SimpleNamespace(x=.7+v.x*size*5/aspect,
                                             y=.55+v.y*size*5, z=0.) for v in world]
                    with self.subTest(gesture=gesture, yaw=yaw, size=size):
                        result = Classifier().classify(image, aspect, world)
                        self.assertEqual(result.gesture, gesture)
                        self.assertEqual(result.features['pose_source'], 'world')
                        self.assertAlmostEqual(result.center[0], sum(image[j].x*aspect
                                               for j in (0, 5, 9, 13, 17))/5)

    def test_bad_world_geometry_falls_back_to_image(self):
        image = hand(Gesture.OPEN)
        world = [SimpleNamespace(x=0., y=0., z=0.)] * 21
        result = Classifier().classify(image, world_landmarks=world)
        self.assertEqual(result.gesture, Gesture.OPEN)
        self.assertEqual(result.features['pose_source'], 'image')

    def test_thumb_opposition_across_palm_is_left_click(self):
        from types import SimpleNamespace
        p=hand(Gesture.LEFT)
        p[1:5]=[SimpleNamespace(x=x,y=y,z=0.) for x,y in ((.46,.73),(.50,.66),(.54,.60),(.59,.53))]
        self.assertEqual(Classifier().classify(p).gesture,Gesture.LEFT)

    def test_ok_pinch_has_priority_over_bent_index(self):
        c=Classifier()
        self.assertEqual(c.classify(hand(Gesture.RIGHT)).gesture,Gesture.RIGHT)
        self.assertEqual(c.classify(hand(Gesture.SCROLL)).gesture,Gesture.SCROLL)

    def test_pinch_hysteresis_and_reset(self):
        c=Classifier()
        self.assertEqual(c.classify(hand(Gesture.SCROLL)).gesture,Gesture.SCROLL)
        p=hand(Gesture.SCROLL); p[4].x += .085
        self.assertEqual(c.classify(p).gesture,Gesture.SCROLL)
        c.reset()
        self.assertNotEqual(c.classify(p).gesture,Gesture.SCROLL)
        p[4].x += .04
        self.assertNotEqual(c.classify(p).gesture,Gesture.SCROLL)

    def test_pinch_requires_other_three_fingers_extended(self):
        p=hand(Gesture.SCROLL); folded=hand(Gesture.FIST)
        p[10:13]=folded[10:13]
        self.assertEqual(Classifier().classify(p).gesture,Gesture.OTHER)

    def test_previous_command_shapes_are_unknown(self):
        for fingers,thumb in (((5,),False),((5,9),False),((),True)):
            p=hand(Gesture.FIST); opened=hand(Gesture.OPEN)
            for mcp in fingers:
                p[mcp+1:mcp+4]=opened[mcp+1:mcp+4]
            if thumb:
                p[1:5]=opened[1:5]
            self.assertEqual(Classifier().classify(p).gesture,Gesture.OTHER)

    def test_all_gestures_rotations_mirrors_scales(self):
        for g in Gesture:
            for rotation in (0.,.6,1.5,3.):
                for mirror in (False,True):
                    for scale in (.7,1.,1.4):
                        with self.subTest(g=g,rotation=rotation,mirror=mirror,scale=scale):
                            self.assertEqual(Classifier().classify(hand(g,rotation=rotation,mirror=mirror,scale=scale)).gesture,g)

    def test_invalid_geometry_rejected(self):
        c=Classifier()
        self.assertIsNone(c.classify([]))
        p=hand(); p[0].x=float('nan')
        self.assertIsNone(c.classify(p))
        p=hand()
        for v in p: v.x=v.y=v.z=0
        self.assertIsNone(c.classify(p))


class MotionTests(unittest.TestCase):
    def test_stationary_no_events(self):
        cfg=Config(); tracker=PalmTracker(cfg); motion=RelativeMotion(cfg)
        rng=random.Random(42); out=[]
        for t in range(0,5000,20):
            point=tracker.update((.5+rng.uniform(-.0005,.0005),.6+rng.uniform(-.0005,.0005)),.24,t)
            out+=motion.move(point,t)
        self.assertEqual(out,[])

    def test_scale_change_without_translation(self):
        tracker=PalmTracker(Config())
        for t in range(0,2000,20):
            self.assertEqual(tracker.update((.5,.6),.24*(1+.15*math.sin(t/300)),t),(0.,0.))

    def trajectory(self, speed, fps):
        cfg=Config(); tracker=PalmTracker(cfg); motion=RelativeMotion(cfg); out=[]
        for i in range(fps*2+1):
            t=i*1000/fps
            p=tracker.update((.4+speed*t/1000,.6),.24,t)
            out+=motion.move(p,t)
        return sum(e[1] for e in out)

    def test_slow_precise_accumulates(self):
        value=self.trajectory(.012,60)
        self.assertGreater(value,.07)
        self.assertLess(value,.25)

    def test_fast_responsive(self):
        self.assertGreater(self.trajectory(.12,60),self.trajectory(.012,60)*10)

    def test_frame_rate_motion_consistency(self):
        values=[self.trajectory(.05,fps) for fps in (15,30,60,120)]
        self.assertLess(max(values)/min(values),1.15)

    def test_outlier_rejected(self):
        tracker=PalmTracker(Config()); tracker.update((.5,.6),.24,0)
        self.assertIsNone(tracker.update((.9,.6),.24,20))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.c=Controller(Config()); self.t=0; self.events=[]

    def feed(self,g,duration=200,**kw):
        for _ in range(duration//20):
            self.events+=self.c.update(hand(g,**kw),self.t)
            self.t+=20

    def test_synthetic_tap_double(self):
        self.feed(Gesture.OPEN,300)
        for _ in range(2):
            self.feed(Gesture.LEFT,120); self.feed(Gesture.OPEN,120)
        self.assertEqual(self.events,[('click','left'),('click','left')])
        self.assertEqual(self.c.engine.double_clicks,1)

    def test_flapping_no_clicks(self):
        self.feed(Gesture.OPEN,300)
        for _ in range(30):
            self.feed(Gesture.LEFT,20); self.feed(Gesture.OPEN,20)
        self.assertEqual(self.events,[])

    def test_loss_recovery_requires_stable_open_hand(self):
        self.feed(Gesture.OPEN,300); self.feed(Gesture.LEFT,850)
        self.events+=self.c.update(None,self.t); self.t+=20
        self.feed(Gesture.LEFT,850)
        self.assertEqual(self.events,[('down','left'),('up','left')])
        self.feed(Gesture.OPEN,300,x=.3)
        self.assertEqual(self.events,[('down','left'),('up','left')])

    def test_scroll_stops_immediately(self):
        self.feed(Gesture.OPEN,300); self.feed(Gesture.SCROLL,200)
        self.feed(Gesture.LEFT,20)
        self.assertEqual(self.c.engine.mode,'IDLE')
        self.assertEqual(self.events,[])

    def test_pause_and_reposition_no_jump(self):
        self.feed(Gesture.OPEN,300); self.feed(Gesture.FIST,200,x=.2)
        self.feed(Gesture.OPEN,400,x=.3)
        self.assertEqual(self.events,[])

    def test_disable_releases(self):
        self.feed(Gesture.OPEN,300); self.feed(Gesture.RIGHT,850)
        self.c.enabled=False
        self.feed(Gesture.RIGHT,20)
        self.assertEqual(self.events,[('down','right'),('up','right')])

    def test_wrong_dominant_hand_rejected(self):
        c=Controller(Config(dominant_hand='Left'))
        self.assertEqual(c.update(hand(),0,handedness='Right'),[])
        self.assertFalse(c.ready)

    def test_tracking_outlier_cancels_pending(self):
        self.feed(Gesture.OPEN,300); self.feed(Gesture.LEFT,100)
        self.feed(Gesture.LEFT,20,x=1.)
        self.assertEqual(self.c.engine.mode,'LOST_HAND')
        self.assertEqual(self.events,[])

    def test_synthetic_right_tap(self):
        self.feed(Gesture.OPEN,300)
        self.feed(Gesture.RIGHT,120)
        self.feed(Gesture.OPEN,120)
        self.assertEqual(self.events,[('click','right')])

    def test_synthetic_scroll_both_directions(self):
        self.feed(Gesture.OPEN,300)
        self.feed(Gesture.SCROLL,200)
        for i in list(range(1,31))+list(range(29,-1,-1)):
            self.feed(Gesture.SCROLL,20,y=-i*.004)
        scrolls=[e[1] for e in self.events if e[0]=='scroll']
        self.assertTrue(any(v>0 for v in scrolls))
        self.assertTrue(any(v<0 for v in scrolls))
        self.assertTrue(all(e[0]=='scroll' for e in self.events))

    def test_synthetic_slow_movement(self):
        self.feed(Gesture.OPEN,300)
        for i in range(1,101):
            self.feed(Gesture.OPEN,20,x=i*.0005)
        self.assertTrue(self.events)
        self.assertTrue(all(e[0]=='move' and e[1]>0 for e in self.events))

    def test_fist_pauses_on_first_frame(self):
        self.feed(Gesture.OPEN,300)
        self.assertTrue(self.c.ready)
        self.feed(Gesture.FIST,20)
        self.assertEqual(self.c.engine.mode,'IDLE')
        self.assertFalse(self.c.ready)
        self.assertEqual(self.events,[])

    def test_original_mapping_recovers_with_fist(self):
        self.c=Controller(Config(move_gesture='FIST'))
        self.feed(Gesture.FIST,300)
        self.assertTrue(self.c.ready)
        self.assertEqual(self.c.engine.mode,'MOVE')
        self.feed(Gesture.OPEN,20)
        self.assertFalse(self.c.ready)
        self.assertEqual(self.c.engine.mode,'IDLE')

    def test_change_from_click_to_ok_cancels_without_click(self):
        self.feed(Gesture.OPEN,300)
        self.feed(Gesture.RIGHT,120)
        self.feed(Gesture.SCROLL,200)
        self.feed(Gesture.OPEN,120)
        self.assertEqual(self.events,[])


class ConfigurationTests(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'config.json'
            cfg=Config(sensitivity=2.,dominant_hand='Left'); cfg.save(path)
            self.assertEqual(Config.load(path),cfg)

    def test_invalid_parameters(self):
        for kw in ({'min_cutoff':0},{'deadzone':-1},{'tap_ms':1000},{'sensitivity':float('nan')},{'dominant_hand':'wrong'},
                   {'pinch_distance':0},{'pinch_release':.2}):
            with self.subTest(kw=kw), self.assertRaises(ValueError): Config(**kw).validate()


if __name__=='__main__': unittest.main()
