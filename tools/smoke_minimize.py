"""Minimize/restore only our own test windows. No camera, clicks or cursor movement."""
import ctypes as ct
from ctypes import wintypes as wt
import json
from pathlib import Path
import sys
from time import monotonic,sleep
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cursor_hud import CursorHud
from window import PreviewWindow,find_owned_window


def main():
 import numpy as np
 api=ct.WinDLL('user32')
 api.ShowWindow.argtypes=(wt.HWND,ct.c_int)
 api.IsWindowVisible.argtypes=(wt.HWND,)
 api.IsIconic.argtypes=(wt.HWND,)
 api.GetForegroundWindow.restype=wt.HWND
 api.GetWindow.argtypes=(wt.HWND,wt.UINT);api.GetWindow.restype=wt.HWND
 api.GetTopWindow.argtypes=(wt.HWND,);api.GetTopWindow.restype=wt.HWND
 api.SetWindowPos.argtypes=(wt.HWND,wt.HWND,ct.c_int,ct.c_int,ct.c_int,ct.c_int,wt.UINT)
 api.PostMessageW.argtypes=(wt.HWND,wt.UINT,wt.WPARAM,wt.LPARAM)
 api.GetDC.argtypes=(wt.HWND,);api.GetDC.restype=wt.HDC
 api.ReleaseDC.argtypes=(wt.HWND,wt.HDC)
 gdi=ct.WinDLL('gdi32');gdi.GetPixel.argtypes=(wt.HDC,ct.c_int,ct.c_int);gdi.GetPixel.restype=wt.DWORD
 preview=PreviewWindow();hud=CursorHud()
 try:
  frame=np.zeros((480,940,3),dtype=np.uint8)
  preview.publish(frame)
  assert preview.rendered.wait(10),'Preview not rendered'
  assert hud.ready.wait(10),'HUD not ready'
  handle=find_owned_window('Invisible Mouse 0.2',preview.process.pid)
  assert handle,'Owned preview not found'
  def pump(duration=.4):
   until=monotonic()+duration
   while monotonic()<until:
    hud.update(True);preview.publish(frame)
    assert ord('q') not in preview.poll(),'Minimization stopped preview'
    sleep(.02)
  def pixel_green():
   point=wt.POINT();api.GetCursorPos(ct.byref(point))
   left,top,width,height=[api.GetSystemMetrics(i) for i in (76,77,78,79)]
   x=point.x+32 if point.x+32<left+width else point.x-32
   dc=api.GetDC(None)
   try:return gdi.GetPixel(dc,x,point.y)==0x0014FF39
   finally:api.ReleaseDC(None,dc)
  def is_above(first,second):
   current=api.GetTopWindow(None)
   while current:
    if current==first:return True
    if current==second:return False
    current=api.GetWindow(current,2)
   return False
  pump()
  results={}
  for i in range(3):
   api.ShowWindow(handle,7);pump()
   results[f'minimize_{i+1}']=bool(api.IsIconic(handle)) and hud.visible.is_set() and pixel_green()
   api.ShowWindow(handle,9);pump()
   results[f'restore_{i+1}']=not api.IsIconic(handle) and hud.visible.is_set() and pixel_green()
  foreground=api.GetForegroundWindow()
  api.ShowWindow(hud.hwnd.value,0);pump()
  results['recovers_forced_hide']=bool(api.IsWindowVisible(hud.hwnd.value)) and pixel_green()
  api.ShowWindow(hud.hwnd.value,7);pump()
  results['recovers_hud_minimize']=not api.IsIconic(hud.hwnd.value) and pixel_green()
  api.SetWindowPos(hud.hwnd.value,wt.HWND(-2),0,0,0,0,0x0010|0x0001|0x0002)
  api.SetWindowPos(handle,wt.HWND(-1),0,0,0,0,0x0010|0x0001|0x0002)
  pump(.6)
  results['recovers_z_order']=is_above(hud.hwnd.value,handle) and pixel_green()
  results['no_focus_theft_during_recovery']=api.GetForegroundWindow()==foreground
  results['controller_preview_alive']=preview.process.is_alive() and not preview.stopped.is_set()
  api.PostMessageW(handle,0x0010,0,0)  # close only the preview owned by this test
  until=monotonic()+2
  closed=False
  while monotonic()<until:
   if ord('q') in preview.poll():
    closed=True
    break
   sleep(.02)
  results['explicit_close_still_exits']=closed
  print(json.dumps(dict(checks=results,hud=hud.status()),indent=2))
  if not all(results.values()):raise RuntimeError('Minimize/visibility regression')
 finally:
  hud.close();preview.close()


if __name__=='__main__':main()
