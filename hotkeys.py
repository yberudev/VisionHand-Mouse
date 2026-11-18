"""Poll only F8/F9 on Windows. No keyboard hooks or typed-text collection."""
import os


class GlobalHotkeys:
    def __init__(self, get_state=None):
        if get_state is None and os.name == 'nt':
            import ctypes
            get_state = ctypes.windll.user32.GetAsyncKeyState
        self.get_state = get_state
        self.previous = set()

    def poll(self):
        if self.get_state is None:
            return []
        down = {code for code in (0x77, 0x78) if self.get_state(code) & 0x8000}
        pressed = down - self.previous
        self.previous = down
        # Exit has priority if both keys were pressed together.
        if 0x78 in pressed:
            return [ord('q')]
        return [ord(' ')] if 0x77 in pressed else []
