"""One-slot capture: drop old frames instead of building a latency queue."""
from threading import Condition, Thread
from time import monotonic


class Capture:
    def __init__(self, camera):
        self.camera = camera
        self.condition = Condition()
        self.latest = None
        self.sequence = 0
        self.failed = False
        self.running = True
        self.capture_ms = 0.
        self.fps = 0.
        self.error = None
        self.thread = Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        previous = None
        try:
            while self.running:
                start = monotonic()
                ok, frame = self.camera.read()
                now = monotonic()
                with self.condition:
                    if not ok:
                        self.failed = True
                        self.condition.notify_all()
                        return
                    self.capture_ms = (now-start)*1000
                    if previous is not None and now > previous:
                        self.fps = 1/(now-previous)
                    previous = now
                    self.latest = (frame, now)
                    self.sequence += 1
                    self.condition.notify_all()
        except Exception as error:
            with self.condition:
                self.error, self.failed = error, True
                self.condition.notify_all()

    def read(self, after):
        with self.condition:
            self.condition.wait_for(lambda: self.sequence > after or self.failed, timeout=.2)
            if self.failed or self.sequence <= after:
                return None
            return self.sequence, self.latest

    def close(self):
        self.running = False
        self.thread.join(timeout=1)
        self.camera.release()
        self.thread.join(timeout=1)
