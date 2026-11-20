import tempfile
from pathlib import Path
import unittest
from types import SimpleNamespace
from main import configure
from config import Config
from controller import Controller
from engine import Gesture
from synthetic import hand


class FistClickTests(unittest.TestCase):
    def setUp(self):
        self.c=Controller(Config(left_click_gesture='FIST'))
        self.t=0
        self.events=[]
        self.feed(Gesture.OPEN,300)

    def feed(self,g,duration=120,**kwargs):
        for _ in range(duration//20):
            self.events+=self.c.update(hand(g,**kwargs),self.t)
            self.t+=20

    def test_single_click(self):
        self.feed(Gesture.FIST)
        self.feed(Gesture.OPEN)
        self.assertEqual(self.events,[('click','left')])

    def test_double_click(self):
        for _ in range(2):
            self.feed(Gesture.FIST);self.feed(Gesture.OPEN)
        self.assertEqual(self.events,[('click','left'),('click','left')])
        self.assertEqual(self.c.engine.double_clicks,1)

    def test_hold_moves_and_releases_on_open_hand(self):
        self.feed(Gesture.FIST,850)
        self.assertEqual(self.events,[('down','left')])
        for i in range(1,30):self.feed(Gesture.FIST,20,x=i*.002)
        self.assertTrue(any(e[0]=='move' for e in self.events))
        self.feed(Gesture.OPEN,x=.058)
        self.assertEqual([e for e in self.events if e[0] in ('down','up')],
                         [('down','left'),('up','left')])
        self.assertFalse(any(e[0]=='click' for e in self.events))

    def test_four_finger_reopening_clicks_before_folded_thumb_pause(self):
        self.feed(Gesture.FIST)
        self.feed(Gesture.LEFT,420)
        self.assertEqual(self.events,[('click','left')])
        self.assertEqual(self.c.engine.mode,'IDLE')
        self.assertEqual(self.c.reason,'pause_gesture')

    def test_confirmed_folded_thumb_releases_hold(self):
        self.feed(Gesture.FIST,850)
        self.feed(Gesture.LEFT,80)
        self.assertEqual(self.events,[('down','left'),('up','left')])

    def test_missing_hand_still_releases(self):
        self.feed(Gesture.FIST,850)
        self.events+=self.c.update(None,self.t)
        self.assertEqual(self.events,[('down','left'),('up','left')])

    def test_right_click_is_unchanged(self):
        self.feed(Gesture.RIGHT);self.feed(Gesture.OPEN)
        self.assertEqual(self.events,[('click','right')])

    def test_closing_fingers_through_unknown_still_allows_click(self):
        self.feed(Gesture.OTHER,80)
        self.feed(Gesture.FIST)
        self.feed(Gesture.OPEN)
        self.assertEqual(self.events,[('click','left')])

    def test_transient_folded_thumb_during_fist_formation_is_not_pause(self):
        self.feed(Gesture.LEFT,20)
        self.feed(Gesture.FIST)
        self.feed(Gesture.OPEN)
        self.assertEqual(self.events,[('click','left')])

    def test_fist_cannot_click_before_open_hand_recovery(self):
        self.c.stop()
        self.feed(Gesture.FIST,1000)
        self.assertEqual(self.events,[])

    def test_fist_click_option_persists_mapping_without_overwriting_calibration(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'config.json'
            Config(sensitivity=2.3).save(path)
            args=SimpleNamespace(config=str(path),set=[],fist_click=True,calibrate=False,save_config=False)
            cfg=configure(args)
            saved=Config.load(path)
            self.assertEqual(cfg.left_click_gesture,'FIST')
            self.assertEqual(saved.left_click_gesture,'FIST')
            self.assertEqual(saved.sensitivity,2.3)

    def test_gesture_binding_persists(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'config.json'
            self.c.cfg.save(path)
            cfg=Config.load(path)
            self.assertEqual(cfg.left_click_gesture,'FIST')
            self.assertEqual(cfg.pause_gesture,'LEFT')

    def test_conflicting_move_and_click_rejected(self):
        with self.assertRaises(ValueError):
            Config(move_gesture='FIST',left_click_gesture='FIST').validate()


if __name__=='__main__':unittest.main()
