"""Smoke-check the installed MediaPipe runtime; optional read-only camera probe.
No images are stored and no mouse backend is imported.
"""
import argparse
import json
from pathlib import Path
import sys
from time import monotonic, perf_counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera',type=int)
    args=parser.parse_args()
    import cv2
    import mediapipe as mp
    import numpy as np
    vision=mp.tasks.vision
    options=vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(Path(__file__).resolve().parents[1]/'models/hand_landmarker.task')),
        running_mode=vision.RunningMode.VIDEO,num_hands=1)
    camera=None
    try:
        if args.camera is not None:
            camera=cv2.VideoCapture(args.camera)
            if not camera.isOpened():
                raise RuntimeError('Camera unavailable')
        rows=[]
        with vision.HandLandmarker.create_from_options(options) as model:
            last=-1
            for _ in range(5):
                start=perf_counter()
                if camera is None:
                    frame=np.zeros((480,640,3),dtype=np.uint8)
                else:
                    ok,frame=camera.read()
                    if not ok: raise RuntimeError('Camera read failed')
                captured=perf_counter()
                image=mp.Image(image_format=mp.ImageFormat.SRGB,data=np.ascontiguousarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)))
                t=max(last+1,int(monotonic()*1000)); last=t
                infer=perf_counter(); result=model.detect_for_video(image,t); end=perf_counter()
                rows.append(dict(capture_ms=round((captured-start)*1000,3),
                                 inference_ms=round((end-infer)*1000,3),hands=len(result.hand_landmarks)))
        print(json.dumps(dict(input='camera' if camera is not None else 'blank',frames=rows),indent=2))
    finally:
        if camera is not None: camera.release()


if __name__=='__main__': main()
