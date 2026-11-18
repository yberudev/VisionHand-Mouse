"""Click-through desktop reticle, isolated from camera and mouse event emission."""
import multiprocessing as mp
import os
from time import monotonic


HUD_STYLE = 0x00080000 | 0x00000020 | 0x08000000 | 0x00000080 | 0x00000008


def hud_visible(active, heartbeat, now, timeout):
    return bool(active) and 0 <= now-heartbeat < timeout


def hand_controls_cursor(controller):
    return (controller.enabled and controller.ready
            and controller.reason in ('active', 'confirming_gesture', 'uncertain_frozen','pause_confirming')
            and controller.engine.mode in ('MOVE', 'LEFT_PENDING', 'RIGHT_PENDING',
                                           'LEFT_DRAG', 'RIGHT_HOLD', 'SCROLL'))


def reticle_geometry(x, y, width, height, half=32):
    """Screen-local guide lines and a box whose centre is the pointer hotspot."""
    gap = half+8
    guides = ((0, y, max(0, x-gap), y),
              (min(width, x+gap), y, width, y),
              (x, 0, x, max(0, y-gap)),
              (x, min(height, y+gap), x, height))
    box = (x-half, y-half, x+half, y+half)
    corners = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            px, py = x+sx*half, y+sy*half
            corners.extend(((px-sx*10, py, px, py), (px, py-sy*10, px, py)))
    return guides, box, corners


def _hud_worker(active, heartbeat, stopped, ready, visible, hwnd_value, recoveries, error, timeout):
    import ctypes as ct
    from ctypes import wintypes as wt
    api = ct.WinDLL('user32', use_last_error=True)
    gdi = ct.WinDLL('gdi32', use_last_error=True)
    kernel = ct.WinDLL('kernel32', use_last_error=True)
    callback_type = ct.WINFUNCTYPE(ct.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

    class WNDCLASS(ct.Structure):
        _fields_ = [('style', wt.UINT), ('proc', callback_type), ('clsExtra', ct.c_int),
                    ('wndExtra', ct.c_int), ('instance', wt.HINSTANCE), ('icon', wt.HANDLE),
                    ('cursor', wt.HANDLE), ('background', wt.HANDLE),
                    ('menu', wt.LPCWSTR), ('name', wt.LPCWSTR)]

    class PAINTSTRUCT(ct.Structure):
        _fields_ = [('hdc', wt.HDC), ('erase', wt.BOOL), ('rect', wt.RECT),
                    ('restore', wt.BOOL), ('update', wt.BOOL), ('reserved', wt.BYTE*32)]

    def bind(library, name, result, *arguments):
        function = getattr(library, name)
        function.restype, function.argtypes = result, arguments
        return function

    bind(kernel, 'GetModuleHandleW', wt.HINSTANCE, wt.LPCWSTR)
    bind(api, 'RegisterClassW', wt.WORD, ct.POINTER(WNDCLASS))
    bind(api, 'UnregisterClassW', wt.BOOL, wt.LPCWSTR, wt.HINSTANCE)
    bind(api, 'CreateWindowExW', wt.HWND, wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
         ct.c_int, ct.c_int, ct.c_int, ct.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, ct.c_void_p)
    bind(api, 'DefWindowProcW', ct.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
    bind(api, 'SetLayeredWindowAttributes', wt.BOOL, wt.HWND, wt.DWORD, wt.BYTE, wt.DWORD)
    bind(api, 'SetWindowPos', wt.BOOL, wt.HWND, wt.HWND, ct.c_int, ct.c_int, ct.c_int, ct.c_int, wt.UINT)
    bind(api, 'ShowWindow', wt.BOOL, wt.HWND, ct.c_int)
    bind(api, 'IsWindowVisible', wt.BOOL, wt.HWND)
    bind(api, 'IsIconic', wt.BOOL, wt.HWND)
    bind(api, 'SetTimer', ct.c_size_t, wt.HWND, ct.c_size_t, wt.UINT, ct.c_void_p)
    bind(api, 'KillTimer', wt.BOOL, wt.HWND, ct.c_size_t)
    bind(api, 'GetMessageW', ct.c_int, ct.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT)
    bind(api, 'TranslateMessage', wt.BOOL, ct.POINTER(wt.MSG))
    bind(api, 'DispatchMessageW', ct.c_ssize_t, ct.POINTER(wt.MSG))
    bind(api, 'DestroyWindow', wt.BOOL, wt.HWND)
    bind(api, 'GetCursorPos', wt.BOOL, ct.POINTER(wt.POINT))
    bind(api, 'InvalidateRect', wt.BOOL, wt.HWND, ct.c_void_p, wt.BOOL)
    bind(api, 'GetDC', wt.HDC, wt.HWND)
    bind(api, 'ReleaseDC', ct.c_int, wt.HWND, wt.HDC)
    bind(api, 'BeginPaint', wt.HDC, wt.HWND, ct.POINTER(PAINTSTRUCT))
    bind(api, 'EndPaint', wt.BOOL, wt.HWND, ct.POINTER(PAINTSTRUCT))
    bind(api, 'FillRect', ct.c_int, wt.HDC, ct.POINTER(wt.RECT), wt.HANDLE)
    bind(gdi, 'CreateSolidBrush', wt.HANDLE, wt.DWORD)
    bind(gdi, 'CreatePen', wt.HANDLE, ct.c_int, ct.c_int, wt.DWORD)
    bind(gdi, 'CreateCompatibleDC', wt.HDC, wt.HDC)
    bind(gdi, 'CreateCompatibleBitmap', wt.HANDLE, wt.HDC, ct.c_int, ct.c_int)
    bind(gdi, 'SelectObject', wt.HANDLE, wt.HDC, wt.HANDLE)
    bind(gdi, 'GetStockObject', wt.HANDLE, ct.c_int)
    bind(gdi, 'DeleteObject', wt.BOOL, wt.HANDLE)
    bind(gdi, 'DeleteDC', wt.BOOL, wt.HDC)
    bind(gdi, 'MoveToEx', wt.BOOL, wt.HDC, ct.c_int, ct.c_int, ct.c_void_p)
    bind(gdi, 'LineTo', wt.BOOL, wt.HDC, ct.c_int, ct.c_int)
    bind(gdi, 'Rectangle', wt.BOOL, wt.HDC, ct.c_int, ct.c_int, ct.c_int, ct.c_int)
    bind(gdi, 'BitBlt', wt.BOOL, wt.HDC, ct.c_int, ct.c_int, ct.c_int, ct.c_int,
         wt.HDC, ct.c_int, ct.c_int, wt.DWORD)
    if hasattr(api, 'SetProcessDpiAwarenessContext'):
        bind(api, 'SetProcessDpiAwarenessContext', wt.BOOL, ct.c_void_p)(ct.c_void_p(-4))
    state = dict(bounds=None, point=None, shown=False, dc=None, bitmap=None, previous=None,
                 last_topmost=0.)
    hwnd = brush = pen = thick = None
    instance = kernel.GetModuleHandleW(None)
    name = f'InvisibleMouseHUD_{os.getpid()}'
    registered = False

    def free_buffer():
        if state['dc']:
            gdi.SelectObject(state['dc'], state['previous'])
            gdi.DeleteObject(state['bitmap'])
            gdi.DeleteDC(state['dc'])
            state['dc'] = state['bitmap'] = state['previous'] = None

    def tick(window):
        if stopped.is_set():
            api.DestroyWindow(window)
            return
        show = hud_visible(active.value, heartbeat.value, monotonic(), timeout)
        point = wt.POINT()
        if not show or not api.GetCursorPos(ct.byref(point)):
            if state['shown']:
                api.ShowWindow(window, 0)
                state['shown'] = False
                visible.clear()
            return
        bounds = tuple(api.GetSystemMetrics(i) for i in (76,77,78,79))
        left, top, width, height = bounds
        if width < 2 or height < 2:
            raise RuntimeError('Invalid HUD desktop bounds')
        if bounds != state['bounds']:
            free_buffer()
            dc = api.GetDC(window)
            try:
                memory = gdi.CreateCompatibleDC(dc)
                bitmap = gdi.CreateCompatibleBitmap(dc,width,height)
            finally:
                api.ReleaseDC(window,dc)
            if not memory or not bitmap:
                if memory: gdi.DeleteDC(memory)
                if bitmap: gdi.DeleteObject(bitmap)
                raise RuntimeError('Cannot allocate HUD graphics buffer')
            previous = gdi.SelectObject(memory,bitmap)
            state.update(dc=memory,bitmap=bitmap,previous=previous,bounds=bounds,point=None)
            if not api.SetWindowPos(window,wt.HWND(-1),left,top,width,height,0x0010):
                raise ct.WinError(ct.get_last_error())
        now = monotonic()
        externally_hidden = state['shown'] and (not api.IsWindowVisible(window) or api.IsIconic(window))
        if not state['shown'] or externally_hidden or now-state['last_topmost'] >= .25:
            if externally_hidden:
                recoveries.value += 1
            if not state['shown'] or externally_hidden:
                api.ShowWindow(window,4)  # SW_SHOWNOACTIVATE
            # Recover z-order/visibility without activating the window. This is
            # independent of whether the camera preview is minimized or covered.
            if not api.SetWindowPos(window,wt.HWND(-1),left,top,width,height,0x0010 | 0x0040):
                raise ct.WinError(ct.get_last_error())
            state['last_topmost'] = now
            api.InvalidateRect(window,None,False)
        position = point.x-left, point.y-top
        if position != state['point'] or not state['shown'] or externally_hidden:
            state['point'] = position
            api.InvalidateRect(window,None,False)
        state['shown'] = bool(api.IsWindowVisible(window)) and not api.IsIconic(window)
        if state['shown']:
            visible.set()
        else:
            visible.clear()

    @callback_type
    def procedure(window,message,wparam,lparam):
        try:
            if message == 0x0084: return -1  # HTTRANSPARENT
            if message == 0x0021: return 3   # MA_NOACTIVATE
            if message == 0x0014: return 1   # background painted in the buffer
            if message == 0x0113:
                tick(window)
                return 0
            if message == 0x0002:
                api.PostQuitMessage(0)
                return 0
            if message == 0x000F:
                paint = PAINTSTRUCT()
                dc = api.BeginPaint(window,ct.byref(paint))
                try:
                    if state['dc'] and state['point'] is not None:
                        _,_,width,height = state['bounds']
                        memory = state['dc']
                        api.FillRect(memory,ct.byref(wt.RECT(0,0,width,height)),brush)
                        old_pen = gdi.SelectObject(memory,pen)
                        old_brush = gdi.SelectObject(memory,gdi.GetStockObject(5))
                        lines,box,accents = reticle_geometry(*state['point'],width,height)
                        for x1,y1,x2,y2 in lines:
                            gdi.MoveToEx(memory,x1,y1,None); gdi.LineTo(memory,x2,y2)
                        gdi.Rectangle(memory,box[0],box[1],box[2]+1,box[3]+1)
                        gdi.SelectObject(memory,thick)
                        for x1,y1,x2,y2 in accents:
                            gdi.MoveToEx(memory,x1,y1,None); gdi.LineTo(memory,x2,y2)
                        gdi.SelectObject(memory,old_pen)
                        gdi.SelectObject(memory,old_brush)
                        gdi.BitBlt(dc,0,0,width,height,memory,0,0,0x00CC0020)
                finally:
                    api.EndPaint(window,ct.byref(paint))
                return 0
            return api.DefWindowProcW(window,message,wparam,lparam)
        except Exception as exception:
            error.value = str(exception).encode('utf-8')[:1000]
            api.DestroyWindow(window)
            return 0

    try:
        brush = gdi.CreateSolidBrush(0)
        pen = gdi.CreatePen(0,1,0x0014FF39)
        thick = gdi.CreatePen(0,3,0x0014FF39)
        cls = WNDCLASS(0,procedure,0,0,instance,None,None,brush,None,name)
        if not api.RegisterClassW(ct.byref(cls)): raise ct.WinError(ct.get_last_error())
        registered = True
        hwnd = api.CreateWindowExW(HUD_STYLE,name,'Invisible Mouse HUD',0x80000000,
                                   0,0,1,1,None,None,instance,None)
        if not hwnd: raise ct.WinError(ct.get_last_error())
        if not api.SetLayeredWindowAttributes(hwnd,0,255,1): raise ct.WinError(ct.get_last_error())
        hwnd_value.value = hwnd
        if not api.SetTimer(hwnd,1,16,None): raise ct.WinError(ct.get_last_error())
        ready.set()
        message = wt.MSG()
        while True:
            status = api.GetMessageW(ct.byref(message),None,0,0)
            if status == -1: raise ct.WinError(ct.get_last_error())
            if status == 0: break
            api.TranslateMessage(ct.byref(message)); api.DispatchMessageW(ct.byref(message))
    except Exception as exception:
        error.value = str(exception).encode('utf-8')[:1000]
        ready.set()
    finally:
        visible.clear()
        if hwnd:
            api.KillTimer(hwnd,1)
            api.DestroyWindow(hwnd)
        free_buffer()
        if registered: api.UnregisterClassW(name,instance)
        for obj in (brush,pen,thick):
            if obj: gdi.DeleteObject(obj)


class CursorHud:
    def __init__(self, timeout=.4):
        if os.name != 'nt':
            raise RuntimeError('The desktop HUD currently supports Windows only')
        context = mp.get_context('spawn')
        self.active = context.Value('b', False, lock=False)
        self.heartbeat = context.Value('d', monotonic(), lock=False)
        self.stopped = context.Event()
        self.ready = context.Event()
        self.visible = context.Event()
        self.hwnd = context.Value('Q', 0, lock=False)
        self.recoveries = context.Value('I', 0, lock=False)
        self.error = context.Array('c', 1024)
        self.process = context.Process(target=_hud_worker,
            args=(self.active, self.heartbeat, self.stopped, self.ready, self.visible,
                  self.hwnd, self.recoveries, self.error, timeout), daemon=True, name='InvisibleMouseHUD')
        self.process.start()

    def update(self, active):
        self.heartbeat.value = monotonic()
        self.active.value = bool(active)
        if self.error.value:
            raise RuntimeError(f"HUD failed: {self.error.value.decode('utf-8', errors='replace')}")
        if not self.process.is_alive():
            raise RuntimeError('HUD process exited unexpectedly')

    def close(self):
        self.active.value = False
        self.stopped.set()
        self.process.join(timeout=.5)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=1)

    def status(self):
        return dict(requested=bool(self.active.value), visible=self.visible.is_set(),
                    alive=self.process.is_alive(), recoveries=self.recoveries.value,
                    heartbeat_age_ms=round((monotonic()-self.heartbeat.value)*1000,1),
                    error=self.error.value.decode('utf-8',errors='replace') or None)
