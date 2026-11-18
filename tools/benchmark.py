"""Deterministic baseline comparison. No camera, external packages or OS events.

The original engine is frozen in tests/baseline_engine.py for reproducibility.
Run from repository root: python tools/benchmark.py
"""
import json
from math import hypot, sin
from pathlib import Path
import random
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from baseline_engine import Engine as Baseline, Gesture as OldGesture
from config import Config
from engine import Engine, Gesture
from motion import PalmTracker


def compare(kind, fps=60):
    rng=random.Random(42)
    old=Baseline(); new=Engine(Config()); tracker=PalmTracker(new.cfg)
    old_events=[]; new_events=[]
    for i in range(fps*5+1):
        t=i*1000/fps
        scale=.24*(1+.025*sin(t/90)) if kind=='stationary' else .24
        speed={'stationary':0.,'slow':.012,'fast':.12}[kind]
        x=(.45 if kind=='stationary' else .25)+speed*t/1000
        y=.55
        if kind=='stationary':
            x+=rng.uniform(-.0005,.0005); y+=rng.uniform(-.0005,.0005)
        old_events+=old.update(OldGesture.FIST,(x/scale,y/scale),t)
        p=tracker.update((x,y),scale,t)
        new_events+=new.update(Gesture(new.cfg.move_gesture),p,t)
    def stats(events):
        moves=[e for e in events if e[0]=='move']
        return dict(move_events=len(moves),path_palm_units=round(sum(hypot(e[1],e[2]) for e in moves),6),
                    net_x_palm_units=round(sum(e[1] for e in moves),6))
    return dict(baseline=stats(old_events),v02=stats(new_events))


if __name__=='__main__':
    print(json.dumps(dict(duration_s=5,seed=42,stationary=compare('stationary'),
                         slow=compare('slow'),fast=compare('fast'),
                         fps_sweep={str(fps):compare('slow',fps)['v02'] for fps in (15,30,60,120)}),indent=2))
