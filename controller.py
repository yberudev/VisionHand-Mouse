"""Landmarks -> safe events, usable in offline replays and camera applications."""
from engine import Engine, Gesture
from gestures import Classifier, Stabilizer
from motion import PalmTracker
from math import isfinite


class Controller:
    def __init__(self, cfg):
        self.cfg = cfg
        self.engine = Engine(cfg)
        self.classifier = Classifier(cfg)
        self.stabilizer = Stabilizer(cfg)
        self.tracker = PalmTracker(cfg)
        self.ready_since = None
        self.ready = False
        self.losses = 0
        self.last_t = None
        self.observation = None
        self.point = None
        self.enabled = True
        self.last_hand = None
        self.reason = 'initializing'
        self.uncertain_since = None
        self.fist_candidate = None
        self.fist_since = None
        self.fist_frames = 0
        self.fist_cycle_start = None

    def stop(self, lost=False, reason=None):
        self.reason = reason or ('tracking_lost' if lost else 'paused')
        if lost and (self.ready or self.ready_since is not None):
            self.losses += 1
        self.ready, self.ready_since = False, None
        self.classifier.reset()
        self.stabilizer.reset()
        self.tracker.reset()
        self.point = None
        self.last_hand = None
        self.uncertain_since = None
        self.fist_candidate = self.fist_since = self.fist_cycle_start = None
        self.fist_frames = 0
        return self.engine.stop(lost)

    def _fist_cycle(self, obs, t):
        """Fast close/open evidence, separate from the general pose stabilizer."""
        if not (self.ready and self.engine.left_gesture == Gesture.FIST
                and self.engine.mode in ('MOVE','LEFT_PENDING','LEFT_DRAG')):
            return None
        opening = obs.features.get('finger_states') == [True,True,True,True]
        signal = Gesture.FIST if obs.gesture == Gesture.FIST else Gesture.OPEN if opening else None
        if signal is None or signal == Gesture.OPEN and self.engine.mode == 'MOVE':
            self.fist_candidate = self.fist_since = None
            self.fist_frames = 0
            return None
        if signal != self.fist_candidate:
            self.fist_candidate, self.fist_since, self.fist_frames = signal, t, 0
        self.fist_frames += 1
        threshold = self.cfg.fist_press_ms if signal == Gesture.FIST else self.cfg.fist_release_ms
        if self.fist_frames < 2 or t-self.fist_since < threshold:
            return self._uncertain(t)
        self.uncertain_since = None
        if signal == Gesture.FIST and self.engine.mode == 'MOVE':
            self.fist_cycle_start = self.fist_since
        allow_tap = self.fist_cycle_start is not None and t-self.fist_cycle_start <= self.cfg.fist_tap_ms
        events = self.engine.update(signal,self.point,t,allow_tap=allow_tap)
        self.reason = 'active'
        if signal == Gesture.OPEN:
            self.fist_cycle_start = None
        return events

    def _uncertain(self, t):
        if self.uncertain_since is None:
            self.uncertain_since = t
        if t-self.uncertain_since >= self.cfg.uncertain_ms:
            return self.stop(reason='uncertainty_timeout')
        self.engine.suspend(self.point, t)
        if self.engine.mode == 'MOVE':
            self.engine.motion.reset(self.point,t)
        self.reason = 'uncertain_frozen'
        return []

    def update(self, landmarks, t, aspect=1., handedness=None, confidence=1., world_landmarks=None):
        gap = self.last_t is not None and (t <= self.last_t or t - self.last_t > self.cfg.max_gap_ms)
        self.last_t = t
        self.observation = None
        if not self.enabled:
            return self.stop(reason='disabled')
        if gap:
            return self.stop(lost=True, reason='timestamp_gap')
        if landmarks is None:
            return self.stop(lost=True, reason='no_hand')
        if not isfinite(confidence) or confidence < .65:
            return self.stop(lost=True, reason='low_confidence')
        if self.last_hand is not None and handedness is not None and self.last_hand != handedness:
            return self.stop(lost=True, reason='hand_changed')
        self.last_hand = handedness
        if self.cfg.dominant_hand != 'any' and handedness != self.cfg.dominant_hand:
            return self.stop(lost=True, reason='wrong_hand')
        obs = self.classifier.classify(landmarks, aspect, world_landmarks)
        self.observation = obs
        if obs is None:
            return self.stop(lost=True, reason='invalid_geometry')
        if obs.tracking_scale < self.cfg.min_palm_scale:
            return self.stop(lost=True, reason='hand_too_far')
        if obs.tracking_scale > self.cfg.max_palm_scale:
            return self.stop(lost=True, reason='hand_too_close')
        self.point = self.tracker.update(obs.center, obs.tracking_scale, t)
        if self.point is None:
            return self.stop(lost=True, reason='motion_outlier')
        stable = self.stabilizer.update(obs.gesture, t)
        fist_events = self._fist_cycle(obs,t)
        if fist_events is not None:
            return fist_events
        if obs.gesture == self.engine.pause_gesture:
            # Closing/opening a fist can briefly resemble a folded thumb. In
            # fist-click mode confirm that replacement pause, freezing meanwhile.
            if self.engine.left_gesture == Gesture.FIST and self.ready:
                if t-self.stabilizer.since < self.cfg.fist_pause_ms:
                    self.uncertain_since = None
                    self.engine.suspend(self.point,t)
                    self.engine.motion.reset(self.point,t)
                    self.reason = 'pause_confirming'
                    return []
            return self.stop(reason='pause_gesture')
        if self.uncertain_since is not None and t-self.uncertain_since >= self.cfg.uncertain_ms:
            return self.stop(reason='uncertainty_timeout')
        if obs.gesture == Gesture.OTHER:
            if (self.engine.mode in ('LEFT_PENDING', 'RIGHT_PENDING', 'LEFT_DRAG', 'RIGHT_HOLD')
                    or self.engine.mode == 'MOVE' and self.engine.left_gesture == Gesture.FIST):
                return self._uncertain(t)
            return self.stop(reason='unknown_gesture')
        if not self.ready:
            self.reason = 'recovering'
            if obs.gesture != self.engine.move_gesture:
                self.ready_since = None
                return []
            if self.ready_since is None:
                self.ready_since = t
            if t - self.ready_since < self.cfg.recover_ms or stable != self.engine.move_gesture:
                return []
            self.ready = True
        # Scroll ends on the first frame outside the OK pinch hysteresis.
        if self.engine.mode == 'SCROLL' and obs.gesture != Gesture.SCROLL:
            self.reason = 'scroll_ended'
            return self.engine.stop()
        # Do not move/click on an unconfirmed transition. Timers remain monotonic.
        if stable is None or obs.gesture != stable:
            if self.engine.mode in ('LEFT_PENDING', 'RIGHT_PENDING', 'LEFT_DRAG', 'RIGHT_HOLD'):
                return self._uncertain(t)
            self.reason = 'confirming_gesture'
            return []
        self.uncertain_since = None
        self.reason = 'active'
        return self.engine.update(stable, self.point, t)
