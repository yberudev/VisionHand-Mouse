"""Camera overlays only; never modify landmarks or mouse control state."""
from math import isfinite
from types import SimpleNamespace


HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
)


def draw_skeleton(frame, landmarks, cv2):
    if landmarks is None or len(landmarks) != 21:
        return
    height, width = frame.shape[:2]
    points = []
    for landmark in landmarks:
        if not isfinite(landmark.x) or not isfinite(landmark.y):
            return
        points.append((round(max(0., min(1., landmark.x)) * (width-1)),
                       round(max(0., min(1., landmark.y)) * (height-1))))
    for start, end in HAND_CONNECTIONS:
        cv2.line(frame, points[start], points[end], (18, 24, 18), 4, cv2.LINE_AA)
        cv2.line(frame, points[start], points[end], (70, 230, 100), 2, cv2.LINE_AA)
    for index, point in enumerate(points):
        color = (255, 255, 255) if index in (4, 8, 12, 16, 20) else (0, 200, 255)
        cv2.circle(frame, point, 4, (25, 25, 25), -1, cv2.LINE_AA)
        cv2.circle(frame, point, 2, color, -1, cv2.LINE_AA)


def hand_detail(frame, landmarks, cv2):
    """Magnify small hands before drawing the skeleton, using the same frame."""
    if landmarks is None or len(landmarks) != 21:
        return None
    height, width = frame.shape[:2]
    points = [(p.x * (width - 1), p.y * (height - 1)) for p in landmarks]
    if not all(isfinite(x) and isfinite(y) for x, y in points):
        return None
    xs, ys = zip(*points)
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    edge = min(height, width)
    if not 4 <= span <= edge * .28 or edge < 120:
        return None
    crop = min(edge, max(36, round(span * 1.55)))
    mid_x, mid_y = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    if not (0 <= mid_x < width and 0 <= mid_y < height):
        return None
    left = min(width - crop, max(0, round(mid_x - crop / 2)))
    top = min(height - crop, max(0, round(mid_y - crop / 2)))
    size = min(192, edge // 2)
    detail = cv2.resize(frame[top:top + crop, left:left + crop], (size, size), interpolation=cv2.INTER_LINEAR)
    points_inside = [SimpleNamespace(x=(x-left)/(crop-1), y=(y-top)/(crop-1)) for x, y in points]
    draw_skeleton(detail, points_inside, cv2)
    # Put the inset opposite the tracked hand to keep its original view clear.
    return detail, mid_x >= width / 2


def gesture_panel(frame, controller, cv2, detail=None):
    """Append a panel so status boxes cannot cover the tracked hand."""
    height, width = frame.shape[:2]
    panel_width = 300
    canvas = cv2.copyMakeBorder(frame, 0, max(0, 480-height), 0, panel_width,
                                cv2.BORDER_CONSTANT, value=(24, 27, 32))
    if detail is not None:
        zoom, on_left = detail
        size = zoom.shape[0]
        x, y = (10 if on_left else width - size - 10), height - size - 10
        canvas[y:y+size, x:x+size] = zoom
        cv2.rectangle(canvas, (x-1, y-1), (x+size, y+size), (82, 186, 113), 1)
        cv2.rectangle(canvas, (x, y), (x+78, y+18), (24, 27, 32), -1)
        cv2.putText(canvas, 'DETALHE', (x+6, y+13), cv2.FONT_HERSHEY_SIMPLEX,
                    .38, (220, 245, 225), 1, cv2.LINE_AA)
    observation = controller.observation
    detected = observation.gesture.value if observation else None
    mode = controller.engine.mode
    move_gesture = controller.cfg.move_gesture
    pause_gesture = controller.cfg.pause_gesture
    left_gesture = controller.cfg.left_click_gesture
    left_actions = {'LEFT_PENDING': 'Clique esquerdo pendente', 'LEFT_DRAG': 'Arrastar: esquerdo premido'}
    rows = (
        ('FIST', 'Esquerdo: punho fechado' if left_gesture == 'FIST' else 'Punho fechado',
         left_actions if left_gesture == 'FIST' else {'MOVE': 'Mover cursor'} if move_gesture == 'FIST' else {}),
        ('LEFT', 'Esquerdo: polegar recolhido' if left_gesture == 'LEFT' else 'Pausa: polegar recolhido',
         left_actions if left_gesture == 'LEFT' else {}),
        ('RIGHT', 'Direito: indicador recolhido', {'RIGHT_PENDING': 'Clique direito pendente', 'RIGHT_HOLD': 'Botao direito premido'}),
        ('SCROLL', 'Scroll: sinal OK', {'SCROLL': 'Scroll vertical'}),
        ('OPEN', 'Mao aberta', {'MOVE': 'Mover cursor'} if move_gesture == 'OPEN' else {}),
        ('OTHER', 'Desconhecido', {}),
    )

    def text(message, x, y, color=(210, 215, 220), size=.43):
        cv2.putText(canvas, message, (x, y), cv2.FONT_HERSHEY_SIMPLEX, size, color, 1, cv2.LINE_AA)

    text('ESTADO DOS GESTOS', width+14, 27, size=.55)
    status = ('DESATIVADO' if not controller.enabled else 'SEM MAO' if observation is None
              else 'APROXIME A MAO' if controller.reason == 'hand_too_far'
              else 'AFASTE A MAO' if controller.reason == 'hand_too_close'
              else 'GESTO INCERTO: CONGELADO' if controller.reason == 'uncertain_frozen'
              else 'EM PAUSA' if detected == pause_gesture
              else 'PRONTO' if controller.ready else 'A RECUPERAR')
    text(status, width+14, 49)
    for index, (gesture, title, actions) in enumerate(rows):
        top = 65 + index*58
        selected = detected == gesture
        color = (70, 230, 100) if selected else (90, 95, 105)
        cv2.rectangle(canvas, (width+10, top), (width+panel_width-10, top+50), color, 1)
        text(title, width+20, top+19, color, .47)
        action = actions.get(mode, 'Inativo')
        if mode in ('LEFT_PENDING', 'RIGHT_PENDING') and mode in actions:
            elapsed = controller.engine.last_t-controller.engine.start
            action = f'Abrir: clique | manter {int(elapsed)}/{controller.cfg.drag_ms}ms'
        if selected:
            if gesture == pause_gesture:
                action = 'Cursor em pausa'
            elif gesture == 'OTHER':
                action = 'Movimento congelado' if controller.reason == 'uncertain_frozen' else 'Acoes canceladas'
            elif not controller.enabled:
                action = 'Controlo desativado'
            elif not controller.ready:
                action = 'Aguardar mao aberta estavel' if move_gesture == 'OPEN' else 'Aguardar punho estavel'
            elif mode not in actions:
                action = 'Detetado: a confirmar'
        text(action, width+20, top+39)
    text(f'Motor: {mode}', width+14, 438)
    text('H: mostrar/ocultar esqueleto', width+14, 463)
    return canvas
