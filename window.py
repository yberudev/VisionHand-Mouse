"""Disposable preview process. A Windows move/size modal loop cannot stall input."""
import multiprocessing as mp
from queue import Empty, Full
import os


def find_owned_window(title, pid):
    """Find only a window belonging to the requested process (multiple instances safe)."""
    import ctypes as ct
    from ctypes import wintypes as wt
    api = ct.WinDLL('user32')
    api.GetWindowThreadProcessId.argtypes = (wt.HWND,ct.POINTER(wt.DWORD))
    api.GetWindowTextW.argtypes = (wt.HWND,wt.LPWSTR,ct.c_int)
    callback_type = ct.WINFUNCTYPE(wt.BOOL,wt.HWND,wt.LPARAM)
    api.EnumWindows.argtypes = (callback_type,wt.LPARAM)
    found = []
    @callback_type
    def visit(hwnd, _):
        owner = wt.DWORD()
        api.GetWindowThreadProcessId(hwnd,ct.byref(owner))
        if owner.value == pid:
            text = ct.create_unicode_buffer(256)
            api.GetWindowTextW(hwnd,text,len(text))
            if text.value == title:
                found.append(hwnd)
                return False
        return True
    api.EnumWindows(visit,0)
    return found[0] if found else None


def _offer(queue, item):
    try:
        queue.put_nowait(item)
    except Full:
        return False
    return True


def _preview_worker(frames, keys, errors, stopped, rendered):
    import cv2
    title = 'Invisible Mouse 0.2'
    shown = False
    native_handle = None
    is_window = None
    is_minimized = None
    if os.name == 'nt':
        import ctypes as ct
        from ctypes import wintypes as wt
        is_window = ct.windll.user32.IsWindow
        is_window.argtypes = (wt.HWND,)
        is_minimized = ct.windll.user32.IsIconic
        is_minimized.argtypes = (wt.HWND,)
    try:
        while not stopped.is_set():
            try:
                frame = frames.get(timeout=.02)
            except Empty:
                frame = None
            minimized = native_handle is not None and is_minimized(native_handle)
            if frame is not None and not minimized:
                cv2.imshow(title, frame)
                shown = True
                rendered.set()
                if is_window and native_handle is None:
                    native_handle = find_owned_window(title,os.getpid())
            key = cv2.waitKey(1)
            if key >= 0:
                _offer(keys, key & 0xFF)
            if key & 0xFF in (ord('q'), 27):
                stopped.set()
            # Visibility is not existence: minimized/hidden previews must not quit input.
            closed = (not is_window(native_handle) if native_handle is not None else
                      shown and is_window is None and cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1)
            if closed:
                stopped.set()
    except Exception as error:
        _offer(errors, repr(error))
        stopped.set()
    finally:
        cv2.destroyAllWindows()


class PreviewWindow:
    def __init__(self):
        context = mp.get_context('spawn')
        self.frames = context.Queue(maxsize=1)
        self.keys = context.Queue(maxsize=32)
        self.errors = context.Queue(maxsize=1)
        self.stopped = context.Event()
        self.rendered = context.Event()
        self.process = context.Process(target=_preview_worker,
                                       args=(self.frames, self.keys, self.errors, self.stopped, self.rendered),
                                       daemon=True, name='InvisibleMousePreview')
        self.process.start()

    def publish(self, frame):
        # Drop previews instead of ever waiting for a moving/minimized window.
        if not _offer(self.frames, frame):
            try:
                self.frames.get_nowait()
            except Empty:
                pass
            _offer(self.frames, frame)

    def poll(self):
        try:
            error = self.errors.get_nowait()
        except Empty:
            error = None
        if error:
            raise RuntimeError(f'Preview failed: {error}')
        keys = []
        while True:
            try:
                keys.append(self.keys.get_nowait())
            except Empty:
                break
        if self.stopped.is_set() or not self.process.is_alive():
            keys.append(ord('q'))
        return keys

    def close(self):
        self.stopped.set()
        self.process.join(timeout=.5)
        if self.process.is_alive():
            # This process owns no camera, model or pressed mouse buttons.
            self.process.terminate()
            self.process.join(timeout=1)
        for queue in (self.frames, self.keys, self.errors):
            queue.cancel_join_thread()
            queue.close()
