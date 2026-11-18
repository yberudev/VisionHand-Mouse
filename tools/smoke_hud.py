"""Show the HUD briefly; verify styles/focus/passthrough without clicking or moving."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
from time import monotonic, sleep
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cursor_hud import CursorHud, HUD_STYLE


def main():
    api=ctypes.WinDLL('user32',use_last_error=True)
    api.GetForegroundWindow.restype=wintypes.HWND
    api.WindowFromPoint.argtypes=(wintypes.POINT,)
    api.WindowFromPoint.restype=wintypes.HWND
    get_style=getattr(api,'GetWindowLongPtrW',api.GetWindowLongW)
    get_style.argtypes=(wintypes.HWND,ctypes.c_int);get_style.restype=ctypes.c_ssize_t
    api.GetDC.argtypes=(wintypes.HWND,);api.GetDC.restype=wintypes.HDC
    api.ReleaseDC.argtypes=(wintypes.HWND,wintypes.HDC)
    gdi=ctypes.WinDLL('gdi32')
    gdi.GetPixel.argtypes=(wintypes.HDC,ctypes.c_int,ctypes.c_int);gdi.GetPixel.restype=wintypes.DWORD
    foreground=api.GetForegroundWindow()
    hud=CursorHud()
    try:
        if not hud.ready.wait(10):raise RuntimeError('HUD startup timed out')
        for _ in range(30):
            hud.update(True)
            sleep(.02)
        if not hud.visible.is_set():raise RuntimeError('HUD did not become visible')
        style=get_style(hud.hwnd.value,-20)
        cursor=wintypes.POINT();api.GetCursorPos(ctypes.byref(cursor))
        left,top,width,height=[api.GetSystemMetrics(i) for i in (76,77,78,79)]
        x=cursor.x+32 if cursor.x+32<left+width else cursor.x-32
        y=cursor.y
        hit=api.WindowFromPoint(wintypes.POINT(x,y))
        dc=api.GetDC(None)
        try:color=gdi.GetPixel(dc,x,y)
        finally:api.ReleaseDC(None,dc)
        result=dict(styles_ok=style & HUD_STYLE==HUD_STYLE,
                    no_focus_change=foreground==api.GetForegroundWindow(),
                    click_through=hit!=hud.hwnd.value,
                    green_pixel=color==0x0014FF39,
                    visible=True)
        hud.update(False)
        until=monotonic()+1
        while hud.visible.is_set() and monotonic()<until:sleep(.02)
        result['hidden_on_pause']=not hud.visible.is_set()
        for _ in range(10):
            hud.update(True)
            sleep(.02)
        # Stop sending heartbeats, as if the controller stalled.
        sleep(.55)
        result['hidden_on_stale_control']=not hud.visible.is_set()
        print(json.dumps(result,indent=2))
        if not all(result.values()):raise RuntimeError('HUD smoke check failed')
    finally:
        hud.close()


if __name__=='__main__':main()
