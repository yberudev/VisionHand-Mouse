"""Replay recorded geometry through the pure controller, never through an OS backend."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config import Config
from controller import Controller


def replay(path, cfg):
    controller=Controller(cfg)
    observed=[];replayed=[];states=Counter();frames=0
    with open(path,encoding='utf-8-sig') as file:
        for line in file:
            try:row=json.loads(line)
            except ValueError:continue  # a partial final line while a session is running
            if 'landmarks' not in row:continue
            frames+=1
            points=[SimpleNamespace(x=x,y=y,z=z) for x,y,z in row['landmarks']] if row['landmarks'] else None
            world = [SimpleNamespace(x=x,y=y,z=z) for x,y,z in (row.get('world_landmarks') or ())]
            controller.enabled=row.get('enabled',True)
            events=controller.update(points,row['t_ms'],row.get('aspect',1.),row.get('handedness'),
                                     row.get('tracking_confidence',1.), world or None)
            observed.extend(tuple(e) for e in row['events'] if e[0]!='move')
            replayed.extend(e for e in events if e[0]!='move')
            states[controller.engine.mode]+=1
    if not frames:raise ValueError('No landmarks recorded; run the app with --record-landmarks --log FILE')
    return dict(frames=frames, observed_events=observed,replayed_events=replayed,states=dict(states),
                note='Replay comparison is not a labelled measurement of user intent.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log');parser.add_argument('--config',default='calibration.fist.json')
    args=parser.parse_args()
    print(json.dumps(replay(args.log,Config.load(args.config)),indent=2))
