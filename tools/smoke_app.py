"""Exercise the actual camera loop without opening a window or emitting OS events."""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import main


def run():
    shown=[]
    class HeadlessPreview:
        def publish(self, frame): shown.append(1)
        def poll(self): return [ord('q')] if len(shown)>=5 else []
        def close(self): pass
    with tempfile.TemporaryDirectory() as temp:
        log=Path(temp)/'session.jsonl'
        argv=['main.py','--mirror','--diagnostics','--log',str(log)]
        with patch.object(sys,'argv',argv), patch.object(main,'PreviewWindow',HeadlessPreview):
            main.main()
        rows=[json.loads(line) for line in log.read_text().splitlines()]
        print(json.dumps(dict(frames=len(rows),states=[r['state'] for r in rows],
                             events=[e for r in rows for e in r['events']],
                             inference_ms=[round(r['timings_ms']['inference'],3) for r in rows]),indent=2))
        if len(rows)!=5:
            raise RuntimeError('Expected five processed frames')


if __name__=='__main__': run()
