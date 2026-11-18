"""Fists need positive finger curl/compactness, not one exact thumb angle."""
import math
from types import SimpleNamespace as Point
import unittest
from config import Config
from controller import Controller
from engine import Gesture
from gestures import Classifier
from synthetic import hand


def natural_fist(rounded=False):
    p=hand(Gesture.FIST)
    # Thumb rests near the palm with almost straight joints, in the old
    # uncertainty band for spread: not definitively "folded" by the old rule.
    p[1:5]=[Point(x=x,y=y,z=0.) for x,y in ((.43,.8),(.39,.72),(.37,.68),(.34,.66))]
    if rounded:
        for mcp in (5,9,13,17):
            x,y=p[mcp].x,p[mcp].y
            direction=1 if mcp in (5,9) else -1
            p[mcp+1:mcp+4]=[Point(x=x,y=y-.08,z=0.),
                Point(x=x+direction*.04,y=y-.12,z=0.),
                Point(x=x+direction*.08,y=y-.12,z=0.)]
    return p


class FistGeometryTests(unittest.TestCase):
    def test_ambiguous_thumb_pose_is_fist_when_compact(self):
        obs=Classifier().classify(natural_fist())
        self.assertIsNone(obs.features['thumb_state'])
        self.assertTrue(obs.features['fist_thumb_compact'])
        self.assertEqual(obs.gesture,Gesture.FIST)

    def test_rounded_fingers_in_old_angle_uncertainty_band(self):
        obs=Classifier().classify(natural_fist(rounded=True))
        self.assertTrue(all(125<b<150 for b in obs.features['finger_bends']))
        self.assertEqual(obs.features['fist_closed_fingers'],4)
        self.assertEqual(obs.gesture,Gesture.FIST)

    def test_fist_variants_across_rigid_rotations_mirrors_and_scales(self):
        for rounded in (False,True):
            for size in (.7,1.,1.5):
                for rotation in (0.,.6,1.5,3.):
                    for mirror in (-1,1):
                        p=natural_fist(rounded)
                        for v in p:
                            x,y=(v.x-.5)*size,(v.y-.6)*size
                            v.x=.5+mirror*(x*math.cos(rotation)-y*math.sin(rotation))
                            v.y=.6+x*math.sin(rotation)+y*math.cos(rotation)
                        with self.subTest(rounded=rounded,size=size,rotation=rotation,mirror=mirror):
                            self.assertEqual(Classifier().classify(p).gesture,Gesture.FIST)

    def test_extending_any_finger_prevents_fist(self):
        for mcp in (5,9,13,17):
            p=natural_fist(True);opened=hand(Gesture.OPEN)
            p[mcp+1:mcp+4]=opened[mcp+1:mcp+4]
            self.assertNotEqual(Classifier().classify(p).gesture,Gesture.FIST)

    def test_thumb_stretched_out_is_not_fist(self):
        p=natural_fist();p[1:5]=hand(Gesture.OPEN)[1:5]
        self.assertEqual(Classifier().classify(p).gesture,Gesture.OTHER)

    def test_collapsed_landmark_chain_cannot_be_a_fist(self):
        p=natural_fist()
        p[6:9]=[Point(x=p[5].x,y=p[5].y,z=p[5].z) for _ in range(3)]
        self.assertEqual(Classifier().classify(p).gesture,Gesture.OTHER)

    def test_natural_fist_sequence_generates_exactly_one_click(self):
        c=Controller(Config(left_click_gesture='FIST'));events=[]
        for t in range(0,700,20):
            p=natural_fist(True) if 300<=t<460 else hand(Gesture.OPEN)
            events+=c.update(p,t)
        self.assertEqual(events,[('click','left')])


if __name__=='__main__':unittest.main()
