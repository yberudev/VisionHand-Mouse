"""Geometric finger classification with a conservative uncertainty band."""
from dataclasses import dataclass, field
from math import acos, degrees, hypot, isfinite, sqrt
from engine import Gesture
from config import Config
from statistics import median


def distance(a, b):
    return sqrt(sum((x-y)**2 for x, y in zip(a, b)))


def angle(a, b, c):
    u, v = tuple(x-y for x,y in zip(a,b)), tuple(x-y for x,y in zip(c,b))
    norm = sqrt(sum(x*x for x in u) * sum(x*x for x in v))
    return degrees(acos(max(-1., min(1., sum(x*y for x,y in zip(u,v)) / norm)))) if norm > 1e-9 else 0.


def palm_geometry(points):
    width = distance(points[5], points[17])
    scale = median((width, .85*distance(points[0], points[9]), .90*distance(points[0], points[13])))
    a = tuple(x-y for x,y in zip(points[5], points[0]))
    b = tuple(x-y for x,y in zip(points[17], points[0]))
    cross = tuple(a[(i+1)%3]*b[(i+2)%3]-a[(i+2)%3]*b[(i+1)%3] for i in range(3))
    valid = scale > 0 and width > .25*scale and hypot(*cross) > .12*scale**2
    return width, scale, valid


@dataclass
class Observation:
    gesture: Gesture
    center: tuple
    scale: float
    confidence: float
    tracking_scale: float
    features: dict = field(default_factory=dict)


class Classifier:
    def __init__(self, cfg=None):
        self.cfg = cfg or Config()
        self.extended = [False] * 5
        self.pinching = False
        self.was_fist = False

    def reset(self):
        self.extended = [False] * 5
        self.pinching = False
        self.was_fist = False

    def classify(self, landmarks, aspect=1., world_landmarks=None):
        if len(landmarks) != 21:
            return None
        p = [(v.x * aspect, v.y, getattr(v, 'z', 0.) * aspect) for v in landmarks]
        if not all(isfinite(x) for v in p for x in v):
            return None
        image_width, tracking_scale, image_valid = palm_geometry(p)
        if tracking_scale < .025:
            return None
        center = tuple(sum(p[j][i] for j in (0,5,9,13,17))/5 for i in (0,1))
        source = 'image'
        scale, pose_scale = image_width, tracking_scale
        if world_landmarks is not None and len(world_landmarks) == 21:
            world = [(v.x, v.y, v.z) for v in world_landmarks]
            if all(value is not None and isfinite(value) for point in world for value in point):
                width, size, valid = palm_geometry(world)
                if valid:
                    p, scale, pose_scale, source = world, width, size, 'world'
        if source == 'image' and not image_valid:
            return None
        palm3 = tuple(sum(p[j][i] for j in (0,5,9,13,17))/5 for i in range(3))
        states = []
        bends, reaches, compactness, closed, validity = [], [], [], [], []
        for n, (mcp,pip,dip,tip) in enumerate(((5,6,7,8),(9,10,11,12),(13,14,15,16),(17,18,19,20)), 1):
            bend = min(angle(p[mcp],p[pip],p[dip]), angle(p[pip],p[dip],p[tip]))
            reach = distance(p[0],p[tip]) / max(distance(p[0],p[pip]), 1e-6)
            extended = bend > (145 if self.extended[n] else 160) and reach > (1.08 if self.extended[n] else 1.15)
            folded = bend < 125 or reach < .98
            bones = [distance(p[a],p[b]) for a,b in ((mcp,pip),(pip,dip),(dip,tip))]
            valid = min(bones) > pose_scale*.025 and .25 < sum(bones)/pose_scale < 3.5
            validity.append(valid)
            tip_palm = distance(p[tip],palm3) / pose_scale
            tip_mcp = distance(p[tip],p[mcp])/pose_scale
            straightness = distance(p[tip],p[mcp])/max(sum(bones),1e-6)
            # Curled fingertips can have ambiguous PIP/DIP angles under occlusion.
            # Accept a second positive cue only when the whole finger is compact.
            compact_curl = bend < 150 and straightness < .82 and tip_palm < .9 and tip_mcp < .85
            closed.append(valid and not extended and (folded or compact_curl)
                          and tip_palm < 1.30 and tip_mcp < 1.15)
            bends.append(round(bend,1)); reaches.append(round(reach,3)); compactness.append(round(tip_palm,3))
            states.append(True if valid and extended else False if valid and folded else None)
            if states[-1] is not None:
                self.extended[n] = states[-1]
        thumb_angle = angle(p[1],p[2],p[3])
        thumb_tip_angle = angle(p[2],p[3],p[4])
        spread = distance(p[4],p[5]) / scale
        # Opposition across the palm also counts as folded: a thumb can be
        # relatively straight at its joints while resting over the palm.
        lateral = sum((p[4][i]-p[5][i])*(p[17][i]-p[5][i]) for i in range(3)) / (scale*scale)
        opposed = lateral > .05 and distance(p[4],p[0]) < distance(p[5],p[0]) * 1.1
        thumb = thumb_angle > (140 if self.extended[0] else 155) and thumb_tip_angle > 150 and spread > (.65 if self.extended[0] else .8)
        thumb = thumb and not opposed
        thumb_folded = opposed or spread < .55 or thumb_tip_angle < 125 or thumb_angle < 125
        states.insert(0, True if thumb else False if thumb_folded else None)
        if states[0] is not None:
            self.extended[0] = states[0]
        # Photo references: thumb folded = left; index folded = right;
        # thumb/index tips touching with the other three fingers up = scroll.
        # Pinch takes priority: bent index in an OK sign is not a right click.
        pinch_limit = self.cfg.pinch_release if self.pinching else self.cfg.pinch_distance
        self.pinching = states[2:] == [True, True, True] and distance(p[4], p[8]) / scale < pinch_limit
        thumb_palm = distance(p[4],palm3)/pose_scale
        # A fist does not require the thumb's joints to match one exact folded
        # pose. It must still lie close to the palm; a thumbs-up is not a fist.
        compact_thumb = thumb_palm < 1.20 and distance(p[4],p[5])/pose_scale < 1.15
        # Retain an already acquired fist through one uncertain (not extended)
        # finger; never use this three-finger rule to enter a new fist.
        retained = (self.was_fist and all(validity) and sum(closed)>=3 and not any(s is True for s in states[1:])
                    and max(compactness)<1.45)
        relaxed_entry = (all(validity) and sum(closed)>=3 and not any(s is True for s in states[1:])
                         and all(ok or bend<135 and reach<1.0 and radius<1.45
                                 for ok,bend,reach,radius in zip(closed,bends,reaches,compactness)))
        fist = (all(closed) or relaxed_entry or retained) and compact_thumb
        self.was_fist = fist
        features = dict(finger_states=states[1:], finger_bends=bends, finger_reach=reaches,
                        tip_palm_distances=compactness, fist_closed_fingers=sum(closed),
                        thumb_state=states[0], thumb_spread=round(spread,3),
                        thumb_palm_distance=round(thumb_palm,3), fist_thumb_compact=compact_thumb,
                        fist_retained=bool(fist and retained and not all(closed)),
                        fist_relaxed_entry=bool(fist and relaxed_entry and not all(closed)),valid_fingers=validity,
                        pose_source=source)
        mapping = {(False,True,True,True,True): Gesture.LEFT,
                   (True,False,True,True,True): Gesture.RIGHT,
                   (True,True,True,True,True): Gesture.OPEN}
        gesture = (Gesture.SCROLL if self.pinching else Gesture.FIST if fist
                   else mapping.get(tuple(states), Gesture.OTHER))
        # Three independent palm spans resist width changes from yaw/noisy MCPs.
        return Observation(gesture, center, image_width, 1. if gesture != Gesture.OTHER else 0., tracking_scale, features)


class Stabilizer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.reset()

    def reset(self):
        self.candidate = self.since = self.stable = None

    def update(self, gesture, t):
        if gesture != self.candidate:
            self.candidate, self.since = gesture, t
        # Pause/unknown stop immediately; the configured movement pose is debounced.
        if gesture in (Gesture.OTHER, Gesture(self.cfg.pause_gesture)):
            self.stable = gesture
            return gesture
        if t - self.since >= self.cfg.gesture_ms:
            self.stable = gesture
        return self.stable
