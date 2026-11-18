"""Synthetic landmarks, with real joint geometry (no camera dependencies)."""
from types import SimpleNamespace
from engine import Gesture


def hand(gesture=Gesture.FIST, x=0., y=0., scale=1., mirror=False, rotation=0.):
    from math import sin, cos
    p = [(0.54,.82,0.)] * 21
    for mcp, px, py in ((5,.42,.55),(9,.50,.53),(13,.58,.55),(17,.66,.60)):
        raised = gesture in (Gesture.OPEN, Gesture.LEFT) or gesture in (Gesture.RIGHT, Gesture.SCROLL) and mcp != 5
        p[mcp] = (px,py,0.)
        if raised:
            p[mcp+1],p[mcp+2],p[mcp+3] = (px,py-.14,0.),(px,py-.25,0.),(px,py-.34,0.)
        else:
            p[mcp+1],p[mcp+2],p[mcp+3] = (px,py-.10,0.),(px,py+.01,0.),(px,py+.08,0.)
    if gesture in (Gesture.RIGHT,Gesture.OPEN):
        p[1:5] = [(.46,.73,0.),(.34,.64,0.),(.24,.565,0.),(.14,.49,0.)]
    else:
        p[1:5] = [(.46,.73,0.),(.38,.66,0.),(.43,.58,0.),(.46,.57,0.)]
    if gesture == Gesture.SCROLL:
        p[1:5] = [(.46,.73,0.),(.37,.69,0.),(.30,.64,0.),(.30,.58,0.)]
        p[6:9] = [(.37,.49,0.),(.32,.53,0.),(.30,.58,0.)]
    if gesture == Gesture.OTHER:
        # Only pinky extended is deliberately unsupported.
        p[18:21] = [(.66,.46,0.),(.66,.35,0.),(.66,.26,0.)]
    result = []
    for px,py,pz in p:
        a,b = (px-.5)*scale,(py-.6)*scale
        a,b = a*cos(rotation)-b*sin(rotation),a*sin(rotation)+b*cos(rotation)
        result.append(SimpleNamespace(x=.5+(-a if mirror else a)+x, y=.6+b+y, z=pz*scale))
    return result
