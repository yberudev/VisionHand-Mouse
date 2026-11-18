"""JSONL diagnostic records; timings are monotonic wall-clock estimates."""
import json
from collections import deque


class Diagnostics:
    def __init__(self, path=None, record_landmarks=False):
        self.file = open(path, 'w', encoding='utf-8') if path else None
        self.recent = deque(maxlen=5)
        self.record_landmarks = record_landmarks

    def record(self, controller, t, events, timings, camera_fps, inference_fps, delivery=None, hud=None,
               landmarks=None, aspect=1., handedness=None, tracking_confidence=1., world_landmarks=None):
        self.recent.extend(events)
        obs = controller.observation
        row = dict(t_ms=t, camera_fps=camera_fps, inference_fps=inference_fps,
                   timings_ms=timings, gesture=obs.gesture.value if obs else 'LOST',
                   state=controller.engine.mode, raw=obs.center if obs else None,
                   filtered=controller.point, speed=controller.tracker.speed,
                   confidence=obs.confidence if obs else 0,
                   stable_ms=t-controller.stabilizer.since if controller.stabilizer.since is not None else 0,
                   gesture_ms=t-controller.engine.start if controller.engine.start is not None else 0,
                   losses=controller.losses, events=events, enabled=controller.enabled,
                   reason=controller.reason, backend=delivery, hud=hud)
        row.update(palm_scale=obs.tracking_scale if obs else None,
                   filtered_scale=controller.tracker.filtered_scale,
                   activation=controller.engine.activation,
                   hold_threshold_ms=controller.cfg.drag_ms,
                   click_window_ms=controller.cfg.tap_ms,
                   uncertainty_ms=t-controller.uncertain_since if controller.uncertain_since is not None else 0)
        row.update(left_click_gesture=controller.cfg.left_click_gesture,
                   pause_gesture=controller.cfg.pause_gesture,
                   geometry=obs.features if obs else None)
        row.update(fist_candidate=controller.fist_candidate.value if controller.fist_candidate else None,
                   fist_candidate_frames=controller.fist_frames,
                   fist_cycle_ms=t-controller.fist_cycle_start if controller.fist_cycle_start is not None else None)
        if self.record_landmarks:
            row.update(landmarks=[[v.x,v.y,getattr(v,'z',0.)] for v in landmarks] if landmarks else None,
                       world_landmarks=[[v.x,v.y,v.z] for v in world_landmarks] if world_landmarks else None,
                       aspect=aspect,handedness=handedness,tracking_confidence=tracking_confidence)
        if self.file:
            self.file.write(json.dumps(row)+'\n')
        return row

    def failure(self, error, delivery):
        if self.file:
            self.file.write(json.dumps(dict(type='error', error=str(error), backend=delivery))+'\n')
            self.file.flush()

    def close(self):
        if self.file:
            self.file.close()
