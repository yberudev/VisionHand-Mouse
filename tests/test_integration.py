import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from backends import SimulatedBackend, SystemBackend
from config import Config
from controller import Controller
from diagnostics import Diagnostics
from engine import Gesture
from synthetic import hand


class BackendTests(unittest.TestCase):
    def fake(self):
        calls=[]
        fake=SimpleNamespace(PAUSE=.1,FAILSAFE=True,
            moveRel=lambda *a,**k:calls.append(('move',a)),
            mouseDown=lambda **k:calls.append(('down',k['button'])),
            mouseUp=lambda **k:calls.append(('up',k['button'])),
            click=lambda **k:calls.append(('click',k['button'])),
            scroll=lambda v:calls.append(('scroll',v)))
        with patch.dict('sys.modules',{'pyautogui':fake}):
            backend=SystemBackend(Config(pixels_per_unit=100))
        return backend,fake,calls

    def test_fractional_pixel_accumulation(self):
        backend,fake,calls=self.fake()
        backend.emit([('move',.0025,0.)]*8)
        self.assertEqual(sum(e[1][0] for e in calls),2)

    def test_exception_after_down_still_releases_with_failsafe(self):
        backend,fake,calls=self.fake()
        def fail(**kwargs): raise RuntimeError('OS error')
        fake.mouseDown=fail
        with self.assertRaises(RuntimeError): backend.emit([('down','left')])
        backend.release_all()
        self.assertEqual(calls,[('up','left')])
        self.assertEqual(backend.held,set())
        self.assertTrue(fake.FAILSAFE)

    def test_release_attempts_both_buttons_after_error(self):
        backend,fake,calls=self.fake()
        backend.held={'left','right'}
        def fail(**kwargs):
            calls.append(('up',kwargs['button']))
            raise RuntimeError('OS error')
        fake.mouseUp=fail
        with self.assertRaises(RuntimeError): backend.release_all()
        self.assertEqual({e[1] for e in calls},{'left','right'})
        self.assertTrue(fake.FAILSAFE)

    def test_simulation_tracks_ownership(self):
        b=SimulatedBackend(); b.emit([('down','left'),('down','right')]); b.release_all()
        self.assertEqual(b.held,set())
        self.assertEqual(b.events[-2:],[('up','left'),('up','right')])


class IntegrationTests(unittest.TestCase):
    def test_jsonl_diagnostics(self):
        c=Controller(Config())
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'diagnostic.jsonl'; d=Diagnostics(path)
            c.update(hand(),0)
            d.record(c,0,[],{'inference':10.},30.,29.)
            d.close()
            row=json.loads(path.read_text())
            self.assertEqual(row['gesture'],'FIST')
            self.assertIn('filtered',row)
            self.assertEqual(row['timings_ms']['inference'],10.)

    def test_full_landmark_hold_at_different_frame_rates(self):
        for fps in (15,30,60,120):
            c=Controller(Config()); events=[]
            for i in range(fps*2):
                t=i*1000/fps
                gesture=Gesture.OPEN if t<400 or t>=1200 else Gesture.LEFT
                events+=c.update(hand(gesture),t)
            self.assertEqual(events,[('down','left'),('up','left')])

    def test_nan_confidence_rejected(self):
        c=Controller(Config())
        self.assertEqual(c.update(hand(),0,confidence=float('nan')),[])
        self.assertEqual(c.engine.mode,'LOST_HAND')

    def test_handedness_switch_releases(self):
        c=Controller(Config()); events=[]
        for t in range(0,1200,20):
            g=Gesture.OPEN if t<300 else Gesture.LEFT
            events+=c.update(hand(g),t,handedness='Right')
        events+=c.update(hand(Gesture.LEFT),1200,handedness='Left')
        self.assertEqual(events,[('down','left'),('up','left')])
        self.assertFalse(c.ready)

    def test_outside_double_window_is_not_counted_as_pair(self):
        c=Controller(Config()); events=[]
        for t in range(0,1600,20):
            g=Gesture.LEFT if 300<=t<420 or 1100<=t<1220 else Gesture.OPEN
            events+=c.update(hand(g),t)
        self.assertEqual(events,[('click','left'),('click','left')])
        self.assertEqual(c.engine.double_clicks,0)


if __name__=='__main__': unittest.main()
