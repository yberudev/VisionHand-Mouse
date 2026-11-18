"""Local detection of two short, bright acoustic impulses."""
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import monotonic

import numpy as np


class SnapPair:
    def __init__(self, sample_rate, sensitivity=1.0):
        self.sample_rate = sample_rate
        self.sensitivity = sensitivity
        self.reset()

    def reset(self):
        self.elapsed = 0.
        self.noise = .003
        self.onset = None
        self.snap_like = False
        self.first = None
        self.cooldown_until = 0.

    def feed(self, samples):
        """Consume a mono block of about 10 ms and report a completed pair."""
        duration = len(samples) / self.sample_rate
        t = self.elapsed
        self.elapsed += duration
        peak = float(np.max(np.abs(samples)))
        rms = float(np.sqrt(np.mean(samples**2)))
        loud = peak >= max(.04, self.noise*8) / self.sensitivity
        # Adapt even when background peaks cross the gate. Cap each update so
        # speech and the impulses themselves cannot suddenly raise the floor.
        target_noise = min(rms, self.noise*2, .025)
        self.noise += .08 * (target_noise-self.noise)
        if loud:
            if self.onset is None:
                self.onset = t
            if not self.snap_like and t-self.onset < .055 and peak >= 2.8*rms:
                power = np.abs(np.fft.rfft(samples))**2
                upper = int(len(samples) * 1800 / self.sample_rate)
                self.snap_like = power[upper:].sum() > .30 * power[1:].sum()
            return False
        if self.onset is None:
            return False
        start, valid = self.onset, self.snap_like and t-self.onset <= .065
        self.onset, self.snap_like = None, False
        if not valid or start < self.cooldown_until:
            return False
        if self.first is None or start-self.first > .70:
            self.first = start
            return False
        if start-self.first < .14:
            return False  # ringing or echo from the first snap
        self.first = None
        self.cooldown_until = t + .85
        return True


class SnapListener:
    def __init__(self, device=None, sensitivity=1.0):
        import sounddevice as sd

        rate = sd.query_devices(device, 'input')['default_samplerate']
        if rate < 8000:
            raise ValueError('Microphone sample rate must be at least 8 kHz')
        self.detector = SnapPair(rate, sensitivity)
        self.blocks = Queue(maxsize=16)
        self.discontinuity = Event()
        self.toggles = Queue(maxsize=1)
        self.stopped = Event()
        self.stream = sd.InputStream(device=device, channels=1, dtype='float32',
                                     samplerate=rate, blocksize=round(rate/100),
                                     callback=self._capture)
        try:
            self.stream.start()
        except Exception:
            self.stream.close()
            raise
        self.worker = Thread(target=self._detect, name='SnapDetector', daemon=True)
        self.worker.start()

    def _capture(self, data, frames, timestamp, status):
        if status:
            self.discontinuity.set()
        try:
            self.blocks.put_nowait(data[:, 0].copy())
        except Full:
            self.discontinuity.set()

    def _detect(self):
        while not self.stopped.is_set():
            try:
                block = self.blocks.get(timeout=.1)
            except Empty:
                continue
            if self.discontinuity.is_set():
                self.discontinuity.clear()
                self.detector.reset()
                while True:
                    try:
                        self.blocks.get_nowait()
                    except Empty:
                        break
                continue
            if self.detector.feed(block):
                try:
                    self.toggles.put_nowait(monotonic())
                except Full:
                    pass

    def poll(self):
        try:
            return monotonic() - self.toggles.get_nowait() <= 1.
        except Empty:
            return False

    def close(self):
        self.stopped.set()
        try:
            self.stream.close()
        finally:
            self.worker.join(timeout=1)
