"""Deterministic interaction state machine. No camera or OS imports."""
from enum import Enum
from math import hypot, isfinite
from config import Config
from motion import RelativeMotion


class Gesture(str, Enum):
    FIST = 'FIST'
    LEFT = 'LEFT'
    RIGHT = 'RIGHT'
    SCROLL = 'SCROLL'
    OPEN = 'OPEN'
    OTHER = 'OTHER'


class Engine:
    def __init__(self, config=None):
        self.cfg = (config or Config()).validate()
        self.move_gesture = Gesture(self.cfg.move_gesture)
        self.pause_gesture = Gesture(self.cfg.pause_gesture)
        self.left_gesture = Gesture(self.cfg.left_click_gesture)
        self.motion = RelativeMotion(self.cfg)
        self.mode = 'IDLE'
        self.previous = self.start = self.origin = self.hold_button = None
        self.last_t = None
        self.scroll_acc = 0.
        self.last_click = None
        self.double_clicks = 0
        self.distance_since = None
        self.activation = None

    def stop(self, lost=False):
        out = [('up', self.hold_button)] if self.hold_button else []
        self.mode = 'LOST_HAND' if lost else 'IDLE'
        self.previous = self.start = self.origin = self.hold_button = None
        self.scroll_acc = 0.
        self.last_click = None
        self.motion.reset()
        self.distance_since = None
        self.activation = None
        return out

    def suspend(self, point, t_ms):
        """Freeze uncertain frames; do not count them towards intentional hold time."""
        if self.start is not None and self.last_t is not None:
            self.start += max(0, t_ms - self.last_t)
        self.last_t = t_ms
        self.distance_since = None
        if self.hold_button:
            self.motion.reset(point, t_ms)

    def _anchor(self, point, t):
        self.previous = point
        self.motion.reset(point, t)

    def update(self, gesture, point, t_ms, allow_tap=True):
        if not isfinite(t_ms):
            return self.stop(lost=True)
        gap = self.last_t is not None and (t_ms <= self.last_t or t_ms - self.last_t > self.cfg.max_gap_ms)
        self.last_t = t_ms
        if gap or point is None or not all(isfinite(v) for v in point):
            return self.stop(lost=True)
        if gesture in (Gesture.OTHER, self.pause_gesture):
            return self.stop()
        if self.mode in ('IDLE', 'LOST_HAND'):
            if gesture == self.move_gesture:
                self.mode = 'MOVE'
                self._anchor(point, t_ms)
            return []
        if self.mode == 'MOVE':
            if gesture == self.move_gesture:
                return self.motion.move(point, t_ms)
            if gesture in (self.left_gesture, Gesture.RIGHT):
                self.mode = 'LEFT_PENDING' if gesture == self.left_gesture else 'RIGHT_PENDING'
                self.start, self.origin = t_ms, point
                self.distance_since, self.activation = None, None
                self._anchor(point, t_ms)
            elif gesture == Gesture.SCROLL:
                self.mode, self.previous, self.scroll_acc = 'SCROLL', point, 0.
            return []
        if self.mode in ('LEFT_PENDING', 'RIGHT_PENDING'):
            expected = self.left_gesture if self.mode == 'LEFT_PENDING' else Gesture.RIGHT
            button = 'left' if self.mode == 'LEFT_PENDING' else 'right'
            duration = t_ms - self.start
            tap_window = self.cfg.fist_tap_ms if expected == Gesture.FIST else self.cfg.tap_ms
            if gesture == self.move_gesture:
                out = []
                if allow_tap and duration <= tap_window:
                    # Two normal OS clicks; never synthesize an additional doubleClick.
                    if self.last_click and self.last_click[0] == button and t_ms - self.last_click[1] <= self.cfg.double_ms:
                        self.double_clicks += 1
                        self.last_click = None
                    else:
                        self.last_click = (button, t_ms)
                    out.append(('click', button))
                self.mode, self.start, self.origin = 'MOVE', None, None
                self._anchor(point, t_ms)
                return out
            if gesture != expected:
                return self.stop()
            travel = hypot(point[0]-self.origin[0], point[1]-self.origin[1])
            # A displacement must never steal the quick-click window.
            if duration > tap_window and travel >= self.cfg.drag_distance:
                if self.distance_since is None:
                    self.distance_since = t_ms
            else:
                self.distance_since = None
            distance_hold = self.distance_since is not None and t_ms-self.distance_since >= self.cfg.drag_confirm_ms
            if duration >= self.cfg.drag_ms or distance_hold:
                self.activation = 'duration' if duration >= self.cfg.drag_ms else 'deliberate_distance'
                self.hold_button = button
                self.mode = 'LEFT_DRAG' if button == 'left' else 'RIGHT_HOLD'
                # Retain pending travel, bounded by max_step on each update.
                return [('down', button)] + self.motion.move(point, t_ms)
            return []
        if self.mode in ('LEFT_DRAG', 'RIGHT_HOLD'):
            expected = self.left_gesture if self.mode == 'LEFT_DRAG' else Gesture.RIGHT
            if gesture == self.move_gesture:
                out = [('up', self.hold_button)]
                self.hold_button = None
                self.mode, self.start, self.origin = 'MOVE', None, None
                self._anchor(point, t_ms)
                return out
            if gesture != expected:
                return self.stop()
            return self.motion.move(point, t_ms)
        if self.mode == 'SCROLL':
            if gesture == self.move_gesture:
                self.mode, self.scroll_acc = 'MOVE', 0.
                self._anchor(point, t_ms)
                return []
            if gesture != Gesture.SCROLL:
                return self.stop()
            dy = point[1] - self.previous[1]
            if abs(dy) <= self.cfg.scroll_deadzone:
                return []
            travel = dy - (self.cfg.scroll_deadzone if dy > 0 else -self.cfg.scroll_deadzone)
            self.previous = (point[0], self.previous[1] + travel)
            self.scroll_acc -= travel * self.cfg.scroll_gain
            steps = int(self.scroll_acc)
            self.scroll_acc -= steps
            return [('scroll', steps)] if steps else []
        return self.stop()
