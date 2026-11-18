"""OS emission isolated from recognition. Fractional pixels are retained."""
from collections import deque
from math import trunc
import os


class SimulatedBackend:
    def __init__(self):
        self.events = []
        self.held = set()

    def emit(self, events):
        for event in events:
            self.events.append(event)
            if event[0] == 'down':
                self.held.add(event[1])
            elif event[0] == 'up':
                self.held.discard(event[1])

    def release_all(self):
        self.emit([('up', b) for b in sorted(self.held)])


class SystemBackend:
    def __init__(self, cfg, failsafe=True, driver=None):
        if driver is None:
            import pyautogui
            driver = pyautogui
        self.pg, self.cfg = driver, cfg
        self.pg.PAUSE = 0
        self.pg.FAILSAFE = failsafe
        self.held = set()
        self.remainder = [0., 0.]
        self.events = deque(maxlen=50)

    def emit(self, events):
        for event in events:
            self.events.append(event)
            kind = event[0]
            if kind == 'move':
                values = [event[i+1] * self.cfg.pixels_per_unit + self.remainder[i] for i in (0,1)]
                pixels = [trunc(v) for v in values]
                self.remainder = [v-p for v,p in zip(values,pixels)]
                if any(pixels):
                    self.pg.moveRel(*pixels, duration=0)
            elif kind == 'down':
                # Record ownership first so cleanup also handles partial failures.
                self.held.add(event[1])
                self.pg.mouseDown(button=event[1])
            elif kind == 'up':
                self.pg.mouseUp(button=event[1])
                self.held.discard(event[1])
            elif kind == 'click':
                self.held.add(event[1])
                self.pg.click(button=event[1])
                self.held.discard(event[1])
            elif kind == 'scroll':
                self.pg.scroll(event[1])

    def release_all(self):
        # The corner failsafe must not prevent releasing our own held buttons.
        failsafe = self.pg.FAILSAFE
        try:
            self.pg.FAILSAFE = False
            errors = []
            for button in tuple(self.held):
                try:
                    self.pg.mouseUp(button=button)
                    self.held.discard(button)
                except Exception as error:
                    errors.append(error)
            if errors:
                raise errors[0]
        finally:
            self.pg.FAILSAFE = failsafe

    def status(self):
        if hasattr(self.pg, 'status'):
            return self.pg.status()
        return dict(driver='PyAutoGUI', delivery='unchecked')


def create_backend(cfg, live=False, failsafe=True, kind='auto'):
    if not live:
        return SimulatedBackend()
    if kind == 'native' or kind == 'auto' and os.name == 'nt':
        from wininput import WindowsMouse
        return SystemBackend(cfg, failsafe, driver=WindowsMouse())
    return SystemBackend(cfg, failsafe)
