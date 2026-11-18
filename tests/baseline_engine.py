"""Pure state machine for an invisible mouse, independent of camera and OS."""
from dataclasses import dataclass
from enum import Enum
from math import hypot


class Gesture(str, Enum):
    FIST = "FIST"
    INDEX = "INDEX"
    TWO = "TWO"
    THUMB = "THUMB"
    OTHER = "OTHER"


@dataclass
class Config:
    tap_ms: int = 230
    drag_ms: int = 350
    drag_distance: float = 0.075  # palm-width units
    double_ms: int = 400
    sensitivity: float = 1.7
    deadzone: float = 0.012
    scroll_gain: float = 9.0


class Engine:
    """Produces events tuples: move(dx,dy), down(button), up(button), click(button), scroll(steps)."""
    def __init__(self, config=None):
        self.cfg = config or Config()
        self.mode = 'IDLE'
        self.previous = None
        self.start = None
        self.origin = None
        self.hold_button = None
        self.scroll_acc = 0.0
        self.last_t = 0

    def stop(self):
        out = []
        if self.hold_button:
            out.append(('up', self.hold_button))
        self.mode, self.previous, self.start, self.origin = 'IDLE', None, None, None
        self.hold_button, self.scroll_acc = None, 0.0
        return out

    def _move(self, p):
        if self.previous is None:
            self.previous = p
            return []
        dx = p[0] - self.previous[0]
        dy = p[1] - self.previous[1]
        self.previous = p
        if hypot(dx, dy) < self.cfg.deadzone:
            return []
        return [('move', dx * self.cfg.sensitivity, dy * self.cfg.sensitivity)]

    def update(self, gesture, point, t_ms):
        """point: tracked palm coordinates normalized by palm size (not screen pixels)."""
        self.last_t = t_ms
        if gesture == Gesture.OTHER or point is None:
            return self.stop()
        out = []
        if self.mode == 'IDLE':
            if gesture == Gesture.FIST:
                self.mode, self.previous = 'MOVE', point
            elif gesture in (Gesture.INDEX, Gesture.TWO):
                # Require FIST as entry state; prevents accidental activation on reacquisition.
                return out
            elif gesture == Gesture.THUMB:
                return out
            return out

        if self.mode == 'MOVE':
            if gesture == Gesture.FIST:
                return self._move(point)
            if gesture in (Gesture.INDEX, Gesture.TWO):
                self.mode = 'LEFT_PENDING' if gesture == Gesture.INDEX else 'RIGHT_PENDING'
                self.start = t_ms
                self.origin = point
                self.previous = point
                return out
            if gesture == Gesture.THUMB:
                self.mode = 'SCROLL'
                self.previous = point
                self.scroll_acc = 0.0
                return out
            return self.stop()

        if self.mode in ('LEFT_PENDING', 'RIGHT_PENDING'):
            expected = Gesture.INDEX if self.mode == 'LEFT_PENDING' else Gesture.TWO
            button = 'left' if expected == Gesture.INDEX else 'right'
            if gesture == Gesture.FIST:
                if t_ms - self.start <= self.cfg.tap_ms:
                    out.append(('click', button))
                self.mode, self.previous = 'MOVE', point
                self.start, self.origin = None, None
                return out
            if gesture != expected:
                return self.stop()
            travel = hypot(point[0] - self.origin[0], point[1] - self.origin[1])
            if t_ms - self.start >= self.cfg.drag_ms or travel >= self.cfg.drag_distance:
                self.hold_button = button
                self.mode = 'LEFT_DRAG' if button == 'left' else 'RIGHT_HOLD'
                out.append(('down', button))
                # Re-anchor without jumping: pending displacement is intentionally discarded.
                self.previous = point
            return out

        if self.mode in ('LEFT_DRAG', 'RIGHT_HOLD'):
            expected = Gesture.INDEX if self.mode == 'LEFT_DRAG' else Gesture.TWO
            if gesture == Gesture.FIST:
                out.append(('up', self.hold_button))
                self.hold_button = None
                self.mode, self.previous = 'MOVE', point
                return out
            if gesture != expected:
                return self.stop()
            return self._move(point)

        if self.mode == 'SCROLL':
            if gesture == Gesture.FIST:
                self.mode, self.previous, self.scroll_acc = 'MOVE', point, 0.0
                return out
            if gesture != Gesture.THUMB:
                return self.stop()
            if self.previous is None:
                self.previous = point
                return out
            dy = point[1] - self.previous[1]
            self.previous = point
            self.scroll_acc -= dy * self.cfg.scroll_gain
            steps = int(self.scroll_acc)
            self.scroll_acc -= steps
            if steps:
                out.append(('scroll', steps))
            return out
        return self.stop()
