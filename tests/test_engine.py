import unittest
from engine import Engine, Gesture
from config import Config


class EngineTests(unittest.TestCase):
    def test_fist_cancels_and_releases_both_holds(self):
        for gesture, button in ((Gesture.LEFT, 'left'), (Gesture.RIGHT, 'right')):
            e = self.armed()
            self.hold(e, gesture)
            self.assertEqual(e.update(Gesture.FIST, (0, 0), 720), [('up', button)])
            self.assertEqual(e.mode, 'IDLE')

    def test_original_mapping_is_configurable(self):
        e = Engine(Config(move_gesture='FIST'))
        self.assertEqual(e.update(Gesture.FIST, (0, 0), 0), [])
        self.assertEqual(e.mode, 'MOVE')
        self.assertTrue(e.update(Gesture.FIST, (.1, 0), 20))
        self.assertEqual(e.update(Gesture.OPEN, (.1, 0), 40), [])
        self.assertEqual(e.mode, 'IDLE')

    def armed(self, **kwargs):
        e = Engine(Config(**kwargs))
        e.update(Gesture.OPEN,(0,0),0)
        return e

    def hold(self, e, gesture=Gesture.LEFT):
        events = e.update(gesture,(0,0),10)
        for t in (100,200,300,400,500,600,700):
            events += e.update(gesture,(0,0),t)
        return events

    def test_tap(self):
        e = self.armed()
        e.update(Gesture.LEFT,(0,0),100)
        self.assertEqual(e.update(Gesture.OPEN,(0,0),200), [('click','left')])
        self.assertEqual(e.update(Gesture.OPEN,(0,0),220), [])

    def test_double_exactly_two_clicks(self):
        e = self.armed(); out=[]
        for t,g in ((50,Gesture.LEFT),(150,Gesture.OPEN),(230,Gesture.LEFT),(330,Gesture.OPEN)):
            out += e.update(g,(0,0),t)
        self.assertEqual(out,[('click','left'),('click','left')])
        self.assertEqual(e.double_clicks,1)

    def test_drag(self):
        e = self.armed()
        self.assertEqual(self.hold(e), [('down','left')])
        self.assertTrue(e.update(Gesture.LEFT,(.1,0),720))
        self.assertEqual(e.update(Gesture.OPEN,(.1,0),740), [('up','left')])

    def test_distance_drag_keeps_pending_travel(self):
        e = self.armed(); e.update(Gesture.LEFT,(0,0),10)
        for t in (100,200,300,400,480):
            self.assertEqual(e.update(Gesture.LEFT,(.2,0),t),[])
        out = e.update(Gesture.LEFT,(.2,0),580)
        self.assertEqual(out[0],('down','left'))
        self.assertGreater(out[1][1],0)

    def test_right_click(self):
        e = self.armed(); e.update(Gesture.RIGHT,(0,0),20)
        self.assertEqual(e.update(Gesture.OPEN,(0,0),120),[('click','right')])

    def test_right_hold(self):
        e = self.armed()
        self.assertEqual(self.hold(e,Gesture.RIGHT),[('down','right')])
        self.assertEqual(e.update(Gesture.OPEN,(0,0),720),[('up','right')])

    def test_loss_and_disable_release_once(self):
        for right in (False,True):
            e=self.armed(); self.hold(e,Gesture.RIGHT if right else Gesture.LEFT)
            self.assertEqual(e.update(Gesture.OTHER,None,720),[('up','right' if right else 'left')])
            self.assertEqual(e.stop(),[])

    def test_pending_cancel_no_click(self):
        e=self.armed(); e.update(Gesture.LEFT,(0,0),10)
        self.assertEqual(e.update(Gesture.FIST,(0,0),50),[])
        self.assertEqual(e.update(Gesture.OPEN,(0,0),100),[])

    def test_fist_pause_reanchor(self):
        e=self.armed(); self.assertEqual(e.update(Gesture.FIST,(4,4),10),[])
        self.assertEqual(e.update(Gesture.OPEN,(20,20),20),[])
        self.assertEqual(e.update(Gesture.OPEN,(20,20),40),[])

    def test_scroll_both_directions_no_cursor(self):
        e=self.armed(); e.update(Gesture.SCROLL,(0,0),10)
        self.assertEqual(e.update(Gesture.SCROLL,(10,-.2),30),[('scroll',1)])
        out=e.update(Gesture.SCROLL,(30,.2),50)
        self.assertTrue(out and out[0][0]=='scroll' and out[0][1]<0)
        self.assertEqual(e.update(Gesture.OPEN,(30,5),70),[])

    def test_scroll_jitter(self):
        e=self.armed(); e.update(Gesture.SCROLL,(0,0),10)
        for t in range(20,1000,20):
            self.assertEqual(e.update(Gesture.SCROLL,(t,.005*(-1)**t),t),[])

    def test_unknown_never_arms(self):
        e=Engine()
        for g in (Gesture.OTHER,Gesture.LEFT,Gesture.RIGHT,Gesture.SCROLL):
            self.assertEqual(e.update(g,(0,0),100),[])

    def test_frame_rates_hold_same_time(self):
        for fps in (15,30,60,120):
            e=self.armed(); e.update(Gesture.LEFT,(0,0),10)
            down=[]
            for i in range(1,fps):
                t=10+i*1000/fps
                events=e.update(Gesture.LEFT,(0,0),t)
                if ('down','left') in events: down.append(t)
            self.assertEqual(len(down),1)
            self.assertGreaterEqual(down[0],10+e.cfg.drag_ms)
            self.assertLessEqual(down[0],10+e.cfg.drag_ms+1000/fps)

    def test_gap_releases_instead_of_hold(self):
        e=self.armed(); self.hold(e)
        self.assertEqual(e.update(Gesture.LEFT,(1,0),1100),[('up','left')])
        self.assertEqual(e.mode,'LOST_HAND')

    def test_nonmonotonic_timestamp_cancels(self):
        e=self.armed(); self.hold(e)
        self.assertEqual(e.update(Gesture.LEFT,(0,0),699),[('up','left')])

    def test_medium_duration_is_neither_click_nor_hold(self):
        e=self.armed(); e.update(Gesture.LEFT,(0,0),10)
        for t in (100,200,300,400): e.update(Gesture.LEFT,(0,0),t)
        self.assertEqual(e.update(Gesture.OPEN,(0,0),550),[])


if __name__=='__main__': unittest.main()
