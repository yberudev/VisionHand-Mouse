import unittest
from types import SimpleNamespace
from cursor_hud import hand_controls_cursor, hud_visible, reticle_geometry
from x11_hud import reticle_rectangles


class CursorHudTests(unittest.TestCase):
    def test_box_is_centered_and_guides_do_not_cross_the_pointer(self):
        guides, box, corners = reticle_geometry(500,300,1920,1080)
        self.assertEqual(box,(468,268,532,332))
        self.assertEqual(len(corners),8)
        self.assertEqual(guides,((0,300,460,300),(540,300,1920,300),
                                 (500,0,500,260),(500,340,500,1080)))

    def test_guides_are_valid_at_all_screen_corners(self):
        for x,y in ((0,0),(1919,0),(0,1079),(1919,1079)):
            guides,box,corners=reticle_geometry(x,y,1920,1080)
            self.assertTrue(all(0<=a<=1920 and 0<=c<=1920 and 0<=b<=1080 and 0<=d<=1080
                                for a,b,c,d in guides))
            self.assertEqual((box[0]+box[2])/2,x)
            self.assertEqual((box[1]+box[3])/2,y)

    def test_x11_overlay_rectangles_are_clipped_to_the_desktop(self):
        for x,y in ((0,0),(199,0),(0,99),(199,99),(100,50)):
            rectangles = reticle_rectangles(x,y,200,100)
            self.assertTrue(rectangles)
            self.assertTrue(all(0 <= left < 200 and 0 <= top < 100
                                and left + width <= 200 and top + height <= 100
                                for left,top,width,height in rectangles))

    def test_stale_or_inactive_control_hides_hud(self):
        self.assertTrue(hud_visible(True,10.,10.1,.4))
        self.assertFalse(hud_visible(False,10.,10.1,.4))
        self.assertFalse(hud_visible(True,10.,10.5,.4))

    def test_pause_loss_and_uncertainty_do_not_show_active_reticle(self):
        c=SimpleNamespace(enabled=True,ready=True,reason='active',engine=SimpleNamespace(mode='MOVE'))
        self.assertTrue(hand_controls_cursor(c))
        for reason in ('disabled','pause_gesture','no_hand'):
            c.reason=reason
            self.assertFalse(hand_controls_cursor(c))
        c.reason='active'; c.engine.mode='IDLE'
        self.assertFalse(hand_controls_cursor(c))

    def test_brief_transitions_do_not_flicker_or_depend_on_preview_state(self):
        c=SimpleNamespace(enabled=True,ready=True,engine=SimpleNamespace(mode='LEFT_DRAG'))
        for reason in ('active','confirming_gesture','uncertain_frozen','pause_confirming'):
            c.reason=reason
            self.assertTrue(hand_controls_cursor(c))
        c.ready=False
        self.assertFalse(hand_controls_cursor(c))


if __name__=='__main__': unittest.main()
