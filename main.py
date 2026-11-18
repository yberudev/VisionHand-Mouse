"""Invisible Mouse 0.2: local webcam control, simulated events by default."""
import argparse
import os
from dataclasses import fields
from pathlib import Path
from time import monotonic, perf_counter, sleep
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
    parser.add_argument('--snap-toggle', action='store_true', help='Toggle camera and mouse with two finger snaps')
    parser.add_argument('--snap-test', action='store_true', help='Test microphone and snap detection without opening the camera')
    parser.add_argument('--start-standby', action='store_true', help='Start with the camera released')
    parser.add_argument('--microphone', type=int, help='Sounddevice input device index for --snap-toggle')
    parser.add_argument('--microphone-mode', choices=('default', 'raw', 'communications', 'compare'),
                        default='default', help='Windows WASAPI capture mode or compare with --snap-test')
    parser.add_argument('--snap-sensitivity', type=float, default=1.0, help='Snap sensitivity from 0.5 to 3.0')
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
    if not .5 <= args.snap_sensitivity <= 3.0:
        parser.error('--snap-sensitivity must be between 0.5 and 3.0')
    if args.microphone_mode == 'compare' and not args.snap_test:
        parser.error('--microphone-mode compare requires --snap-test')
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
    if args.snap_test:
        try:
            from snaps import compare_microphone_modes, test_microphone
            if args.microphone_mode == 'compare':
                compare_microphone_modes(args.microphone, args.snap_sensitivity)
            else:
                test_microphone(args.microphone, args.snap_sensitivity, args.microphone_mode)
        except (ImportError, OSError, RuntimeError, ValueError) as error:
            raise SystemExit(f'Teste de estalos indisponivel: {error}')
        return
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
    capture = None
    listener = None
    window = None
    hud = None
    hud_error = None
    hotkeys = GlobalHotkeys()
    show_skeleton = True
    sequence, last_timestamp, previous_infer = 0, -1, None
    standby_text = 'CAMERA LIBERADA'
    standby_refresh = 0.

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

    def deactivate(message='CAMERA LIBERADA'):
        nonlocal capture, standby_refresh, standby_text
        controller.enabled = False
        controller.stop(reason='standby')
        controller.observation = None
        update_hud(False)
        standby_refresh = 0.
        standby_text = message
        try:
            backend.release_all()
        finally:
            if capture is not None:
                closing, capture = capture, None
                closing.close()

    def activate():
        nonlocal capture, sequence, previous_infer, standby_text, standby_refresh
        camera = cv2.VideoCapture(args.camera)
        try:
            if not camera.isOpened():
                standby_text = f'CAMERA {args.camera} INDISPONIVEL'
                standby_refresh = 0.
                print(f'{standby_text}. Fecha a aplicacao que a usa e tenta novamente.', flush=True)
                return
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            capture = Capture(camera)
        finally:
            if capture is None:
                camera.release()
        sequence, previous_infer = 0, None
        controller.last_t = None
        controller.enabled = True
        print('Controlo ativo. Mostra a mao aberta para comecar.', flush=True)

    def handle_keys():
        nonlocal show_skeleton
        keys = hotkeys.poll() + (window.poll() if window else [])
        if any(key in (ord('q'), 27) for key in keys):
            return False
        snap = listener is not None and listener.poll()
        if snap:
            print('Par de estalos detetado.', flush=True)
        if snap or ord(' ') in keys:
            if capture is None:
                activate()
            else:
                deactivate()
                print('Modo de espera. Camera liberada.', flush=True)
        for key in keys:
            if key == ord('d'):
                args.diagnostics = not args.diagnostics
            elif key == ord('h'):
                show_skeleton = not show_skeleton
            elif key == ord('s'):
                cfg.save(args.config)
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
        if args.snap_toggle:
            try:
                from snaps import SnapListener
                listener = SnapListener(args.microphone, args.snap_sensitivity, args.microphone_mode)
                print(f'Microfone ativo: {listener.description}. Dois estalos alternam o controlo.', flush=True)
            except (ImportError, OSError, RuntimeError, ValueError) as error:
                print(f'Detecao de estalos indisponivel: {error}. Usa F8 ou Espaco.', flush=True)
        print('Windows: F8 ativa/desativa | F9 sai. Na janela: Espaco alterna | Q/ESC sai.', flush=True)
        vision = mp.tasks.vision
        options = vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=args.model),
            running_mode=vision.RunningMode.VIDEO, num_hands=1,
            min_hand_detection_confidence=.65, min_hand_presence_confidence=.65,
            min_tracking_confidence=.6)
        controller.enabled = False
        if not args.start_standby:
            activate()
        with vision.HandLandmarker.create_from_options(options) as landmarker:
            while True:
                if not handle_keys():
                    break
                if capture is None:
                    now = monotonic()
                    if window and now >= standby_refresh:
                        standby = np.zeros((480, 640, 3), dtype=np.uint8)
                        cv2.putText(standby, standby_text, (26, 100), cv2.FONT_HERSHEY_SIMPLEX,
                                    .95, (85, 245, 145), 2, cv2.LINE_AA)
                        keys = 'Dois estalos, F8 ou Espaco para ativar' if listener else 'F8 ou Espaco para ativar'
                        cv2.putText(standby, keys, (26, 145), cv2.FONT_HERSHEY_SIMPLEX,
                                    .66, (210, 215, 220), 1, cv2.LINE_AA)
                        if listener:
                            cv2.putText(standby, listener.meter(), (26, 185), cv2.FONT_HERSHEY_SIMPLEX,
                                        .48, (150, 220, 185), 1, cv2.LINE_AA)
                        window.publish(gesture_panel(standby, controller, cv2))
                        standby_refresh = now + .25
                    sleep(.025)
                    continue
                sample = capture.read(sequence)
                if sample is None:
                    backend.emit(controller.stop(lost=True))
                    backend.release_all()
                    update_hud(False)
                    if capture.failed:
                        print(f'Captura interrompida: {capture.error or "sem frames"}. Tenta reativar.', flush=True)
                        deactivate('CAPTURA INTERROMPIDA')
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
            deactivate()
        finally:
            try:
                if listener:
                    listener.close()
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
