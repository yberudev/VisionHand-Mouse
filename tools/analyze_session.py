"""Summarize an existing JSONL without guessing whether a gesture was intended."""
import argparse
from collections import Counter
import json
from statistics import median


def summarize(path):
    frames=[]; errors=[]; malformed=0
    with open(path, encoding='utf-8-sig') as file:
        for line in file:
            try:
                row=json.loads(line)
            except ValueError:
                malformed+=1
                continue
            if row.get('type') == 'error':
                errors.append(row.get('error'))
            elif 'state' in row:
                frames.append(row)
    actions=[]; held={}
    for row in frames:
        for event in row.get('events', []):
            if event[0] in ('down','up','click'):
                action=dict(t_ms=row['t_ms'], event=event, reason=row.get('reason'),
                            pending_ms=row.get('gesture_ms'), activation=row.get('activation'))
                if event[0]=='down':
                    held[event[1]]=row['t_ms']
                elif event[0]=='up' and event[1] in held:
                    action['held_ms']=row['t_ms']-held.pop(event[1])
                actions.append(action)
    scales=[r['palm_scale'] for r in frames if r.get('palm_scale') is not None]
    return dict(frames=len(frames), states=dict(Counter(r['state'] for r in frames)),
                reasons=dict(Counter(r.get('reason','unavailable') for r in frames)),
                events=dict(Counter(e[0] for r in frames for e in r.get('events',[]))),
                actions=actions, errors=errors, malformed_lines=malformed,
                palm_scale=dict(min=min(scales),median=median(scales),max=max(scales)) if scales else None,
                note='Observed events only. False-click rate requires labelled user intent.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log')
    print(json.dumps(summarize(parser.parse_args().log),indent=2))
