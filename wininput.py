"""Checked SendInput adapter for Windows; supports the whole virtual desktop."""
import ctypes
from ctypes import wintypes
import os


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG),
                ('mouseData', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD),
                ('dwExtraInfo', ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg', wintypes.DWORD), ('wParamL', wintypes.WORD), ('wParamH', wintypes.WORD)]


class _InputUnion(ctypes.Union):
    _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT), ('hi', HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ('data',)
    _fields_ = [('type', wintypes.DWORD), ('data', _InputUnion)]


class InputDeliveryError(RuntimeError):
    pass


class WindowsMouse:
    """PyAutoGUI-shaped adapter, sharing the existing ownership/cleanup logic."""
    PAUSE = 0
    FAILSAFE = True

    def __init__(self, api=None):
        if api is None:
            if os.name != 'nt':
                raise RuntimeError('The native backend requires Windows')
            api = ctypes.WinDLL('user32', use_last_error=True)
            api.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
            api.SendInput.restype = wintypes.UINT
            api.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
            api.GetCursorPos.restype = wintypes.BOOL
            api.GetForegroundWindow.restype = wintypes.HWND
            api.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
            if hasattr(api, 'SetProcessDpiAwarenessContext'):
                api.SetProcessDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
                api.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            else:
                api.SetProcessDPIAware()
        self.api = api
        self.sent = 0
        self.last_status = 'ready'

    def _position(self):
        point = wintypes.POINT()
        if not self.api.GetCursorPos(ctypes.byref(point)):
            raise InputDeliveryError('Cannot read the cursor on the current input desktop')
        return point.x, point.y

    def _bounds(self):
        return tuple(self.api.GetSystemMetrics(i) for i in (76, 77, 78, 79))

    def _send(self, flags, x=0, y=0, data=0):
        if self.FAILSAFE:
            px, py = self._position()
            left, top, width, height = self._bounds()
            if px in (left, left+width-1) and py in (top, top+height-1):
                raise InputDeliveryError('Screen-corner failsafe triggered; use --no-failsafe for this experiment')
        event = INPUT(type=0, mi=MOUSEINPUT(x, y, data & 0xFFFFFFFF, flags, 0, 0))
        if self.api.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
            self.last_status = 'rejected'
            raise InputDeliveryError('Windows rejected mouse input. Check whether the target is elevated '
                                     'or the secure desktop is active; SendInput cannot bypass UIPI.')
        self.sent += 1
        self.last_status = 'accepted'

    def moveRel(self, dx, dy, duration=0):
        px, py = self._position()
        left, top, width, height = self._bounds()
        if width < 2 or height < 2:
            raise InputDeliveryError('Invalid virtual desktop dimensions')
        px = min(left+width-1, max(left, px+dx))
        py = min(top+height-1, max(top, py+dy))
        # Absolute injection avoids applying Windows relative acceleration a second time.
        x = round((px-left)*65535/(width-1))
        y = round((py-top)*65535/(height-1))
        self._send(0x0001 | 0x8000 | 0x4000, x, y)

    def mouseDown(self, button):
        self._send({'left': 0x0002, 'right': 0x0008}[button])

    def mouseUp(self, button):
        self._send({'left': 0x0004, 'right': 0x0010}[button])

    def click(self, button):
        self.mouseDown(button)
        self.mouseUp(button)

    def scroll(self, steps):
        self._send(0x0800, data=steps*120)

    def status(self):
        pid = wintypes.DWORD()
        hwnd = self.api.GetForegroundWindow()
        if hwnd:
            self.api.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return dict(driver='SendInput', delivery=self.last_status, sent=self.sent,
                    foreground_pid=pid.value)
