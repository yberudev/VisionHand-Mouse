"""Transparent, click-through cursor reticle for composited X11 desktops."""
import ctypes as ct
from ctypes.util import find_library
import signal
from time import monotonic, sleep

from cursor_hud import hud_visible, reticle_geometry


def _line_rectangle(x1, y1, x2, y2, thickness):
    if y1 == y2:
        return min(x1, x2), y1 - thickness // 2, abs(x2 - x1) + 1, thickness
    if x1 == x2:
        return x1 - thickness // 2, min(y1, y2), thickness, abs(y2 - y1) + 1
    raise ValueError('Reticle segments must be horizontal or vertical')


def reticle_rectangles(x, y, width, height, half=32):
    """Return clipped rectangles that draw the guides, box and corner accents."""
    guides, box, corners = reticle_geometry(x, y, width, height, half)
    lines = [(segment, 1) for segment in guides]
    x1, y1, x2, y2 = box
    lines.extend((((x1, y1, x2, y1), 1), ((x1, y2, x2, y2), 1),
                  ((x1, y1, x1, y2), 1), ((x2, y1, x2, y2), 1)))
    lines.extend((segment, 3) for segment in corners)

    rectangles = []
    for segment, thickness in lines:
        left, top, rect_width, rect_height = _line_rectangle(*segment, thickness)
        right = min(width, left + rect_width)
        bottom = min(height, top + rect_height)
        left, top = max(0, left), max(0, top)
        if right > left and bottom > top:
            rectangles.append((left, top, right - left, bottom - top))
    return rectangles


class _XVisualInfo(ct.Structure):
    _fields_ = [('visual', ct.c_void_p), ('visualid', ct.c_ulong), ('screen', ct.c_int),
                ('depth', ct.c_int), ('visual_class', ct.c_int), ('red_mask', ct.c_ulong),
                ('green_mask', ct.c_ulong), ('blue_mask', ct.c_ulong),
                ('colormap_size', ct.c_int), ('bits_per_rgb', ct.c_int)]


class _XSetWindowAttributes(ct.Structure):
    _fields_ = [('background_pixmap', ct.c_ulong), ('background_pixel', ct.c_ulong),
                ('border_pixmap', ct.c_ulong), ('border_pixel', ct.c_ulong),
                ('bit_gravity', ct.c_int), ('win_gravity', ct.c_int),
                ('backing_store', ct.c_int), ('backing_planes', ct.c_ulong),
                ('backing_pixel', ct.c_ulong), ('save_under', ct.c_int),
                ('event_mask', ct.c_long), ('do_not_propagate_mask', ct.c_long),
                ('override_redirect', ct.c_int), ('colormap', ct.c_ulong),
                ('cursor', ct.c_ulong)]


class _XRenderColor(ct.Structure):
    _fields_ = [('red', ct.c_ushort), ('green', ct.c_ushort),
                ('blue', ct.c_ushort), ('alpha', ct.c_ushort)]


class _XRenderDirectFormat(ct.Structure):
    _fields_ = [('red', ct.c_short), ('red_mask', ct.c_short),
                ('green', ct.c_short), ('green_mask', ct.c_short),
                ('blue', ct.c_short), ('blue_mask', ct.c_short),
                ('alpha', ct.c_short), ('alpha_mask', ct.c_short)]


class _XRenderPictFormat(ct.Structure):
    _fields_ = [('format_id', ct.c_ulong), ('format_type', ct.c_int),
                ('depth', ct.c_int), ('direct', _XRenderDirectFormat),
                ('colormap', ct.c_ulong)]


def _bind(library, name, result, *arguments):
    function = getattr(library, name)
    function.restype = result
    function.argtypes = arguments
    return function


def _x11_api():
    x11_path = find_library('X11')
    xext_path = find_library('Xext')
    xrender_path = find_library('Xrender')
    if not all((x11_path, xext_path, xrender_path)):
        raise RuntimeError('X11 HUD needs libX11, libXext and libXrender')
    x11, xext, xrender = (ct.CDLL(path) for path in (x11_path, xext_path, xrender_path))
    display = ct.c_void_p
    window = ct.c_ulong

    _bind(x11, 'XOpenDisplay', display, ct.c_char_p)
    _bind(x11, 'XDefaultScreen', ct.c_int, display)
    _bind(x11, 'XRootWindow', window, display, ct.c_int)
    _bind(x11, 'XDisplayWidth', ct.c_int, display, ct.c_int)
    _bind(x11, 'XDisplayHeight', ct.c_int, display, ct.c_int)
    _bind(x11, 'XMatchVisualInfo', ct.c_int, display, ct.c_int, ct.c_int,
          ct.c_int, ct.POINTER(_XVisualInfo))
    _bind(x11, 'XCreateColormap', ct.c_ulong, display, window, ct.c_void_p, ct.c_int)
    _bind(x11, 'XCreateWindow', window, display, window, ct.c_int, ct.c_int,
          ct.c_uint, ct.c_uint, ct.c_uint, ct.c_int, ct.c_uint, ct.c_void_p,
          ct.c_ulong, ct.POINTER(_XSetWindowAttributes))
    _bind(x11, 'XStoreName', ct.c_int, display, window, ct.c_char_p)
    _bind(x11, 'XMapRaised', ct.c_int, display, window)
    _bind(x11, 'XUnmapWindow', ct.c_int, display, window)
    _bind(x11, 'XRaiseWindow', ct.c_int, display, window)
    _bind(x11, 'XDestroyWindow', ct.c_int, display, window)
    _bind(x11, 'XFreeColormap', ct.c_int, display, ct.c_ulong)
    _bind(x11, 'XFlush', ct.c_int, display)
    _bind(x11, 'XSync', ct.c_int, display, ct.c_int)
    _bind(x11, 'XCloseDisplay', ct.c_int, display)
    _bind(x11, 'XQueryPointer', ct.c_int, display, window,
          ct.POINTER(window), ct.POINTER(window), ct.POINTER(ct.c_int),
          ct.POINTER(ct.c_int), ct.POINTER(ct.c_int), ct.POINTER(ct.c_int),
          ct.POINTER(ct.c_uint))
    _bind(x11, 'XInternAtom', ct.c_ulong, display, ct.c_char_p, ct.c_int)
    _bind(x11, 'XGetSelectionOwner', window, display, ct.c_ulong)
    _bind(xext, 'XShapeQueryExtension', ct.c_int, display,
          ct.POINTER(ct.c_int), ct.POINTER(ct.c_int))
    _bind(xext, 'XShapeQueryVersion', ct.c_int, display,
          ct.POINTER(ct.c_int), ct.POINTER(ct.c_int))
    _bind(xext, 'XShapeCombineRectangles', ct.c_int, display, window, ct.c_int,
          ct.c_int, ct.c_int, ct.c_void_p, ct.c_int, ct.c_int, ct.c_int)
    _bind(xrender, 'XRenderQueryExtension', ct.c_int, display,
          ct.POINTER(ct.c_int), ct.POINTER(ct.c_int))
    _bind(xrender, 'XRenderFindVisualFormat', ct.c_void_p, display, ct.c_void_p)
    _bind(xrender, 'XRenderCreatePicture', ct.c_ulong, display, window,
          ct.c_void_p, ct.c_ulong, ct.c_void_p)
    _bind(xrender, 'XRenderFreePicture', ct.c_int, display, ct.c_ulong)
    _bind(xrender, 'XRenderFillRectangle', ct.c_int, display, ct.c_int,
          ct.c_ulong, ct.POINTER(_XRenderColor), ct.c_int, ct.c_int,
          ct.c_uint, ct.c_uint)
    return x11, xext, xrender


def _create_overlay(x11, xext, xrender, display):
    screen = x11.XDefaultScreen(display)
    root = x11.XRootWindow(display, screen)
    width, height = x11.XDisplayWidth(display, screen), x11.XDisplayHeight(display, screen)
    if width < 2 or height < 2:
        raise RuntimeError('X11 reports invalid desktop dimensions')

    compositor_atom = x11.XInternAtom(display, f'_NET_WM_CM_S{screen}'.encode(), 0)
    if not x11.XGetSelectionOwner(display, compositor_atom):
        raise RuntimeError('X11 HUD needs a running compositing manager')

    event_base, error_base = ct.c_int(), ct.c_int()
    if not xrender.XRenderQueryExtension(display, ct.byref(event_base), ct.byref(error_base)):
        raise RuntimeError('X11 server does not support the RENDER extension')
    if not xext.XShapeQueryExtension(display, ct.byref(event_base), ct.byref(error_base)):
        raise RuntimeError('X11 server does not support the SHAPE extension')
    major, minor = ct.c_int(), ct.c_int()
    if not xext.XShapeQueryVersion(display, ct.byref(major), ct.byref(minor)) or (major.value, minor.value) < (1, 1):
        raise RuntimeError('X11 server needs SHAPE 1.1 for click-through input')

    visual = _XVisualInfo()
    if not x11.XMatchVisualInfo(display, screen, 32, 4, ct.byref(visual)):
        raise RuntimeError('X11 server has no 32-bit ARGB visual for a transparent HUD')
    colormap = x11.XCreateColormap(display, root, visual.visual, 0)
    attributes = _XSetWindowAttributes()
    attributes.background_pixel = 0
    attributes.border_pixel = 0
    attributes.override_redirect = 1
    attributes.colormap = colormap
    mask = (1 << 1) | (1 << 3) | (1 << 9) | (1 << 13)
    overlay = x11.XCreateWindow(display, root, 0, 0, width, height, 0, 32, 1,
                                visual.visual, mask, ct.byref(attributes))
    if not overlay:
        x11.XFreeColormap(display, colormap)
        raise RuntimeError('Could not create the X11 HUD window')
    x11.XStoreName(display, overlay, b'Invisible Mouse HUD')
    # An empty ShapeInput region lets all pointer events reach the desktop below.
    xext.XShapeCombineRectangles(display, overlay, 2, 0, 0, None, 0, 0, 0)
    format_info = xrender.XRenderFindVisualFormat(display, visual.visual)
    if not format_info:
        x11.XDestroyWindow(display, overlay)
        x11.XFreeColormap(display, colormap)
        raise RuntimeError('Could not find the X11 ARGB render format')
    if not ct.cast(format_info, ct.POINTER(_XRenderPictFormat)).contents.direct.alpha_mask:
        x11.XDestroyWindow(display, overlay)
        x11.XFreeColormap(display, colormap)
        raise RuntimeError('The selected X11 visual has no alpha channel')
    picture = xrender.XRenderCreatePicture(display, overlay, format_info, 0, None)
    if not picture:
        x11.XDestroyWindow(display, overlay)
        x11.XFreeColormap(display, colormap)
        raise RuntimeError('Could not create the X11 HUD drawing surface')
    return screen, root, width, height, overlay, colormap, picture


def _draw(xrender, display, picture, x, y, width, height):
    green = _XRenderColor(0x1414, 0xFFFF, 0x3939, 0xFFFF)
    clear = _XRenderColor(0, 0, 0, 0)
    xrender.XRenderFillRectangle(display, 0, picture, ct.byref(clear), 0, 0, width, height)
    for left, top, rect_width, rect_height in reticle_rectangles(x, y, width, height):
        xrender.XRenderFillRectangle(display, 1, picture, ct.byref(green),
                                     left, top, rect_width, rect_height)


def run_x11_hud(active, heartbeat, stopped, ready, visible, window_id,
                recoveries, error, timeout):
    """Spawn target compatible with CursorHud; draws only while its heartbeat is fresh."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    display = None
    overlay = colormap = picture = None
    mapped = False
    try:
        x11, xext, xrender = _x11_api()
        display = x11.XOpenDisplay(None)
        if not display:
            raise RuntimeError('Could not connect to the X11 display')
        screen, root, width, height, overlay, colormap, picture = _create_overlay(
            x11, xext, xrender, display)
        window_id.value = overlay
        ready.set()
        last_raise = 0.
        last_point = None

        while not stopped.is_set():
            now = monotonic()
            show = hud_visible(active.value, heartbeat.value, now, timeout)
            if show:
                if not mapped:
                    x11.XMapRaised(display, overlay)
                    mapped = True
                    last_point = None
                elif now - last_raise >= .25:
                    x11.XRaiseWindow(display, overlay)
                last_raise = now

                pointer_root, pointer_child = ct.c_ulong(), ct.c_ulong()
                root_x, root_y = ct.c_int(), ct.c_int()
                win_x, win_y, mask = ct.c_int(), ct.c_int(), ct.c_uint()
                if x11.XQueryPointer(display, root, ct.byref(pointer_root), ct.byref(pointer_child),
                                     ct.byref(root_x), ct.byref(root_y), ct.byref(win_x),
                                     ct.byref(win_y), ct.byref(mask)):
                    point = root_x.value, root_y.value
                    if point != last_point:
                        _draw(xrender, display, picture, *point, width, height)
                        x11.XFlush(display)
                        last_point = point
                    visible.set()
                else:
                    visible.clear()
            else:
                if mapped:
                    x11.XUnmapWindow(display, overlay)
                    x11.XFlush(display)
                    mapped = False
                    last_point = None
                visible.clear()
            sleep(.016)
    except Exception as exception:
        error.value = str(exception).encode('utf-8')[:1000]
        ready.set()
    finally:
        visible.clear()
        if display:
            if picture:
                xrender.XRenderFreePicture(display, picture)
            if overlay:
                x11.XDestroyWindow(display, overlay)
            if colormap:
                x11.XFreeColormap(display, colormap)
            x11.XCloseDisplay(display)
