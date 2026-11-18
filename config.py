"""Validated, persistent calibration. Distances use palm widths; time uses ms."""
from dataclasses import asdict, dataclass, fields
import json
import math
from pathlib import Path


@dataclass
class Config:
    tap_ms: int = 450
    drag_ms: int = 650
    drag_distance: float = 0.18
    drag_confirm_ms: int = 100
    uncertain_ms: int = 180
    min_palm_scale: float = 0.07
    max_palm_scale: float = 0.70
    scale_smoothing_ms: int = 250
    double_ms: int = 400
    sensitivity: float = 1.7
    deadzone: float = 0.012
    acceleration: float = 0.35
    min_cutoff: float = 1.8
    beta: float = 0.7
    scroll_gain: float = 9.0
    scroll_deadzone: float = 0.025
    gesture_ms: int = 45
    recover_ms: int = 150
    max_gap_ms: int = 250
    max_speed: float = 12.0
    max_step: float = 0.6
    pixels_per_unit: float = 120.0
    dominant_hand: str = 'any'
    move_gesture: str = 'OPEN'
    left_click_gesture: str = 'LEFT'
    fist_press_ms: int = 20
    fist_release_ms: int = 20
    fist_tap_ms: int = 600
    fist_pause_ms: int = 350
    pinch_distance: float = 0.30
    pinch_release: float = 0.42

    @property
    def pause_gesture(self):
        if self.move_gesture == 'FIST':
            return 'OPEN'
        return 'LEFT' if self.left_click_gesture == 'FIST' else 'FIST'

    def validate(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name == 'left_click_gesture':
                if value not in ('LEFT', 'FIST'):
                    raise ValueError('left_click_gesture must be LEFT or FIST')
            elif field.name == 'move_gesture':
                if value not in ('OPEN', 'FIST'):
                    raise ValueError('move_gesture must be OPEN or FIST')
            elif field.name == 'dominant_hand':
                if value not in ('any', 'Left', 'Right'):
                    raise ValueError('dominant_hand must be any, Left or Right')
            elif not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f'Invalid {field.name}: {value}')
        for name in ('min_cutoff', 'max_gap_ms', 'max_speed', 'max_step', 'pixels_per_unit'):
            if getattr(self, name) <= 0:
                raise ValueError(f'{name} must be positive')
        if self.drag_ms < self.tap_ms:
            raise ValueError('drag_ms must be >= tap_ms')
        if self.move_gesture == self.left_click_gesture:
            raise ValueError('Movement and left click must use different gestures')
        if self.left_click_gesture == 'FIST' and self.fist_tap_ms >= self.drag_ms:
            raise ValueError('fist_tap_ms must be < drag_ms in fist-click mode')
        if not 0 < self.min_palm_scale < self.max_palm_scale:
            raise ValueError('Require 0 < min_palm_scale < max_palm_scale')
        if self.uncertain_ms >= self.max_gap_ms:
            raise ValueError('uncertain_ms must be < max_gap_ms')
        if self.pinch_distance <= 0 or self.pinch_release <= self.pinch_distance:
            raise ValueError('pinch_release must be > pinch_distance > 0')
        return self

    @classmethod
    def load(cls, path):
        p = Path(path)
        return cls(**json.loads(p.read_text(encoding='utf-8'))).validate() if p.exists() else cls()

    def save(self, path):
        self.validate()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        temp = p.with_suffix(p.suffix + '.tmp')
        temp.write_text(json.dumps(asdict(self), indent=2) + '\n', encoding='utf-8')
        temp.replace(p)
