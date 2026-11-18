"""Invisible Mouse 0.2: local webcam control, simulated events by default."""
import argparse
import os
from dataclasses import fields
from pathlib import Path
from time import monotonic, perf_counter
from config import Config
from controller import Controller
from backends import create_backend
from capture import Capture
from diagnostics import Diagnostics
from preview import draw_skeleton, gesture_panel, hand_detail
from window import PreviewWindow
from hotkeys import GlobalHotkeys
from cursor_hud import CursorHud, hand_controls_cursor


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Emit actual OS events')
    parser.add_argument('--no-failsafe', action='store_true',
                        help='Disable the screen-corner stop')
    parser.add_argument('--backend', choices=('auto', 'native', 'pyautogui'), default='auto',
                        help='auto uses checked SendInput on Windows')
    parser.add_argument('--no-preview', action='store_true', help='Run without a preview window; Windows F8 pauses, F9 exits')
    parser.add_argument('--no-hud', action='store_true', help='Disable the green desktop cursor reticle (Windows live mode)')
    parser.add_argument('--fist-click', action='store_true',
                        help='Experiment: fist left-click/hold, folded thumb pause, open hand movement')
    parser.add_argument('--model', default=str(Path(__file__).parent / 'models/hand_landmarker.task'))
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--mirror', action='store_true')
    parser.add_argument('--config', default='calibration.json')
    parser.add_argument('--calibrate', action='store_true', help='Edit and save calibration, then exit')
    parser.add_argument('--set', action='append', default=[], metavar='NAME=VALUE')
    parser.add_argument('--save-config', action='store_true')
    parser.add_argument('--diagnostics', action='store_true')
    parser.add_argument('--log', help='Write per-frame JSONL diagnostics')
    parser.add_argument('--record-landmarks', action='store_true',
                        help='Include image and 3D hand landmarks in --log for offline calibration (no images)')
    args = parser.parse_args()
    if args.record_landmarks and not args.log:
        parser.error('--record-landmarks requires --log')
    return args


def configure(args):
    cfg = Config.load(args.config)
    names = {f.name: f for f in fields(cfg)}
    for item in args.set:
        name, value = item.split('=', 1)
        if name not in names:
            raise ValueError(f'Unknown parameter: {name}')
        setattr(cfg, name, type(getattr(cfg, name))(value))
    if args.fist_click:
        cfg.left_click_gesture = 'FIST'
    if args.calibrate:
        print('Distances: palm widths; times: milliseconds. Enter keeps the current value.')
        for name in names:
            current = getattr(cfg, name)
            value = input(f'{name} [{current}]: ').strip()
            if value:
                setattr(cfg, name, type(current)(value))
    cfg.validate()
    if args.calibrate or args.save_config:
        cfg.save(args.config)
        print(f'Calibration saved: {args.config}')
    return cfg


def main():
    args = arguments()
    try:
        cfg = configure(args)
    except (ValueError, TypeError) as error:
        raise SystemExit(f'Invalid calibration: {error}')
    if args.calibrate:
        return
    import cv2
    import mediapipe as mp
    import numpy as np
    if not Path(args.model).is_file():
        raise SystemExit(f'Missing model: {args.model}')
    controller = Controller(cfg)
    backend = create_backend(cfg, args.live, not args.no_failsafe, args.backend)
    diagnostics = Diagnostics(args.log,record_landmarks=args.record_landmarks)
    camera = None
    capture = None
    window = None
    hud = None
    hud_error = None
    hotkeys = GlobalHotkeys()
    show_skeleton = True

    def update_hud(active):
        nonlocal hud, hud_error
        if hud:
            try:
                hud.update(active)
            except RuntimeError as error:
                hud_error = str(error)
                print(f'HUD disabled: {error}', flush=True)
                hud.close()
                hud = None

    def handle_keys():
        nonlocal show_skeleton
        keys = hotkeys.poll() + (window.poll() if window else [])
        if any(key in (ord('q'), 27) for key in keys):
            return False
        for key in keys:
            if key == ord('d'):
                args.diagnostics = not args.diagnostics
            elif key == ord('h'):
                show_skeleton = not show_skeleton
            elif key == ord('s'):
                cfg.save(args.config)
            elif key == ord(' '):
                controller.enabled = not controller.enabled
                backend.emit(controller.stop())
                backend.release_all()
                update_hud(False)
        return True

    try:
        if args.live and os.name == 'nt' and not args.no_hud:
            try:
                hud = CursorHud(timeout=max(.4, cfg.max_gap_ms/1000+.1))
            except (OSError, RuntimeError) as error:
                hud_error = str(error)
                print(f'HUD disabled: {error}', flush=True)
        if not args.no_preview:
            window = PreviewWindow()
        print('Windows: F8 pause/resume | F9 exit (global). Preview: SPACE pause | Q/ESC exit.', flush=True)
        vision = mp.tasks.vision
        options = vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=args.model),
            running_mode=vision.RunningMode.VIDEO, num_hands=1,
            min_hand_detection_confidence=.65, min_hand_presence_confidence=.65,
            min_tracking_confidence=.6)
        camera = cv2.VideoCapture(args.camera)
        if not camera.isOpened():
            raise RuntimeError('Could not open camera')
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        capture = Capture(camera)
        sequence, last_timestamp, previous_infer = 0, -1, None
        with vision.HandLandmarker.create_from_options(options) as landmarker:
            while True:
                if not handle_keys():
                    break
                sample = capture.read(sequence)
                if sample is None:
                    backend.emit(controller.stop(lost=True))
                    backend.release_all()
                    update_hud(False)
                    if capture.failed:
                        if capture.error:
                            raise capture.error
                        break
                    continue
                sequence, (frame, captured_at) = sample
                start = perf_counter()
                if args.mirror:
                    frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
                timestamp = max(int(captured_at*1000), last_timestamp+1)
                last_timestamp = timestamp
                infer_start = perf_counter()
                result = landmarker.detect_for_video(image, timestamp)
                infer_end = perf_counter()
                fps = 1/(infer_end-previous_infer) if previous_infer else 0.
                previous_infer = infer_end
                landmarks = result.hand_landmarks[0] if result.hand_landmarks else None
                world_hands = getattr(result, 'hand_world_landmarks', None)
                world_landmarks = world_hands[0] if landmarks and world_hands else None
                hand = result.handedness[0][0] if result.handedness else None
                # Reject stale observations before any event is generated.
                if (monotonic()-captured_at)*1000 > cfg.max_gap_ms:
                    landmarks = None
                    world_landmarks = None
                # Dominant-hand selection uses the model label on the displayed input.
                label = hand.category_name if hand else None
                events = controller.update(landmarks, timestamp, frame.shape[1]/frame.shape[0],
                                           label, hand.score if hand else 0., world_landmarks)
                control_end = perf_counter()
                backend.emit(events)
                update_hud(hand_controls_cursor(controller))
                dispatch_end = perf_counter()
                if not args.live:
                    if events:
                        print('SIM:', events)
                    # Bound memory in an indefinitely running simulated camera session.
                    backend.events.clear()
                timings = dict(capture=capture.capture_ms, preprocess=(infer_start-start)*1000,
                               inference=(infer_end-infer_start)*1000,
                               control=(control_end-infer_end)*1000,
                               dispatch=(dispatch_end-control_end)*1000,
                               frame_age=(monotonic()-captured_at)*1000)
                delivery = backend.status() if hasattr(backend, 'status') else {'driver': 'simulated'}
                hud_status = hud.status() if hud else {'enabled': False, 'error': hud_error}
                row = diagnostics.record(controller, timestamp, events, timings, capture.fps, fps, delivery, hud_status,
                                         landmarks,frame.shape[1]/frame.shape[0],label,hand.score if hand else 0.,
                                         world_landmarks=world_landmarks)
                if window is None:
                    continue
                if show_skeleton:
                    detail = hand_detail(frame, landmarks, cv2)
                    draw_skeleton(frame, landmarks, cv2)
                else:
                    detail = None
                lines = [f"{row['gesture']} | {row['state']} | {'LIVE' if args.live else 'SIM'} | {'ON' if controller.enabled else 'PAUSED'}",
                         'F8 pause | F9 exit (global) | D diagnostics | S save calibration']
                if args.diagnostics:
                    lines += [f"camera {capture.fps:.1f} FPS | inference {fps:.1f} FPS | age {timings['frame_age']:.1f}ms",
                              'stage ms: ' + ' '.join(f'{k}={v:.1f}' for k,v in timings.items() if k != 'frame_age'),
                              f"raw {row['raw']} | filtered {row['filtered']}",
                              f"speed {row['speed']:.3f} palm/s | confidence {row['confidence']:.1f} | stable {row['stable_ms']}ms",
                              f"gesture {row['gesture_ms']}ms | losses {row['losses']} | doubles {controller.engine.double_clicks}",
                              f"{delivery['driver']} | {delivery.get('delivery', 'simulated')} | {row['reason']}",
                              (f"pose {row['geometry']['pose_source']} | fist fingers {row['geometry']['fist_closed_fingers']}/4 | thumb compact {row['geometry']['fist_thumb_compact']}"
                               if row['geometry'] else 'geometry unavailable'),
                              f'events {list(diagnostics.recent)}']
                for i, line in enumerate(lines):
                    cv2.putText(frame, line, (10, 25+i*26), cv2.FONT_HERSHEY_SIMPLEX, .43, (0,220,130), 1)
                preview = gesture_panel(frame, controller, cv2, detail)
                window.publish(preview)
    except Exception as error:
        diagnostics.failure(error, backend.status() if hasattr(backend, 'status') else {})
        raise
    finally:
        # Always release owned buttons even if recognition, dispatch or logging fails.
        try:
            controller.stop()
            backend.release_all()
        finally:
            try:
                if capture:
                    capture.close()
                elif camera is not None:
                    camera.release()
            finally:
                try:
                    if window:
                        window.close()
                finally:
                    try:
                        if hud:
                            hud.close()
                    finally:
                        diagnostics.close()


if __name__ == '__main__':
    main()
