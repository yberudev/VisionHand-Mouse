"""One Euro filtering and scale-normalized translation, independent of camera resolution."""
from math import exp, hypot, pi


def alpha(cutoff, dt):
    return 1 / (1 + 1 / (2 * pi * cutoff * dt))


class PalmTracker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.reset()

    def reset(self):
        self.raw = self.filtered = self.integrated = None
        self.scale = self.t = None
        self.filtered_scale = None
        self.velocity = (0., 0.)
        self.speed = 0.

    def update(self, center, scale, t):
        if self.raw is None:
            self.raw, self.scale, self.t = center, scale, t
            self.filtered_scale = scale
            self.filtered = self.integrated = (0., 0.)
            return self.filtered
        dt = (t - self.t) / 1000
        if dt <= 0 or dt * 1000 > self.cfg.max_gap_ms:
            self.reset()
            return None
        # Normalize differences, never absolute coordinates: depth changes no longer
        # multiply the distance from the image origin into artificial translation.
        s = (scale + self.scale) / 2
        delta = tuple((center[i] - self.raw[i]) / s for i in range(2))
        if hypot(*delta) / dt > self.cfg.max_speed or not .65 < scale / self.scale < 1.55:
            self.reset()
            return None
        smoothing = self.cfg.scale_smoothing_ms / 1000
        weight = 1 - exp(-dt / smoothing) if smoothing > 0 else 1.
        self.filtered_scale += weight * (scale-self.filtered_scale)
        delta = tuple((center[i]-self.raw[i]) / self.filtered_scale for i in range(2))
        a = alpha(1., dt)
        self.velocity = tuple(v + a * (d / dt - v) for v, d in zip(self.velocity, delta))
        self.speed = hypot(*self.velocity)
        self.integrated = tuple(p + d for p, d in zip(self.integrated, delta))
        a = alpha(self.cfg.min_cutoff + self.cfg.beta * self.speed, dt)
        self.filtered = tuple(f + a * (p - f) for f, p in zip(self.filtered, self.integrated))
        self.raw, self.scale, self.t = center, scale, t
        return self.filtered


class RelativeMotion:
    def __init__(self, cfg):
        self.cfg = cfg
        self.anchor = None
        self.t = None
        self.noise = 0.
        self.sample = None
        self.speed = 0.

    def reset(self, point=None, t=None):
        self.anchor, self.t, self.noise = point, t, 0.
        self.sample, self.speed = point, 0.

    def move(self, point, t):
        if self.anchor is None:
            self.reset(point, t)
            return []
        dt = max((t - self.t) / 1000, .001)
        speed = hypot(point[0] - self.sample[0], point[1] - self.sample[1]) / dt
        self.speed += (1 - exp(-dt / .06)) * (speed - self.speed)
        self.sample, self.t = point, t
        dx, dy = point[0] - self.anchor[0], point[1] - self.anchor[1]
        distance = hypot(dx, dy)
        # A stationary anchor accumulates slow deliberate movement across frames.
        if distance < self.cfg.deadzone:
            self.noise += (1 - exp(-dt / .3)) * (distance - self.noise)
        threshold = self.cfg.deadzone + min(self.noise * .5, self.cfg.deadzone * .5)
        if distance <= threshold:
            return []
        # Continuous soft dead zone; preserve subpixel remainder in the backend.
        travel = min(distance - threshold, self.cfg.max_step)
        gain = self.cfg.sensitivity * (1 + self.cfg.acceleration * min(self.speed, 4.))
        self.anchor = (self.anchor[0] + dx * travel / distance,
                       self.anchor[1] + dy * travel / distance)
        self.t = t
        return [('move', dx / distance * travel * gain, dy / distance * travel * gain)]
