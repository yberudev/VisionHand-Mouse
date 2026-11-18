"""Native preview IPC and Windows ABI checks; no clicks, holds or scrolls."""
import ctypes
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import numpy as np
    from window import PreviewWindow
    from wininput import INPUT, WindowsMouse
    # This SendInput packet keeps the cursor at its current position.
    # It tests OS acceptance without clicking/holding or intentionally moving it.
    driver = WindowsMouse()
    driver.FAILSAFE = False
    driver.moveRel(0, 0)
    window = PreviewWindow()
    try:
        frame = np.zeros((480, 940, 3), dtype=np.uint8)
        window.publish(frame)
        if not window.rendered.wait(timeout=10):
            window.poll()
            raise RuntimeError('Preview did not render a frame')
        print(json.dumps(dict(input_size=ctypes.sizeof(INPUT),
                              native=driver.status(), preview_rendered=True), indent=2))
    finally:
        window.close()


if __name__ == '__main__':
    main()
