import ctypes
from ctypes import wintypes
import os
from queue import Queue
import unittest
from unittest.mock import patch

from backends import SystemBackend, SimulatedBackend, create_backend
from config import Config
from controller import Controller
from engine import Gesture
from hotkeys import GlobalHotkeys
from synthetic import hand
from wininput import WindowsMouse, INPUT, InputDeliveryError
from window import PreviewWindow


def blocked_preview(frames, keys, errors, stopped, rendered):
    # Simulate a modal native window loop that never consumes preview frames.
    stopped.wait()


class FakeUser32:
    def __init__(self):
        self.events = []
        self.accept = True
        self.position = (100, 100)
        self.foreground = 123
        self.bounds = (-1920, 0, 3840, 1080)

    def GetSystemMetrics(self, code):
        return dict(zip((76, 77, 78, 79), self.bounds))[code]

    def GetCursorPos(self, pointer):
        p = ctypes.cast(pointer, ctypes.POINTER(wintypes.POINT)).contents
        p.x, p.y = self.position
        return 1

    def SendInput(self, count, pointer, size):
        event = ctypes.cast(pointer, ctypes.POINTER(INPUT)).contents
        self.events.append((event.mi.dwFlags, event.mi.dx, event.mi.dy, event.mi.mouseData))
        return count if self.accept else 0

    def GetForegroundWindow(self):
        return self.foreground

    def GetWindowThreadProcessId(self, hwnd, pointer):
        ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD)).contents.value = hwnd
        return 1


class NativeInputTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeUser32()
        self.driver = WindowsMouse(self.api)
        self.backend = SystemBackend(Config(pixels_per_unit=100), False, self.driver)

    def test_correct_windows_abi_size(self):
        if os.name == 'nt':
            self.assertEqual(ctypes.sizeof(INPUT), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)

    def test_drag_events_and_release_after_foreground_changes(self):
        self.backend.emit([('down', 'left')])
        self.api.foreground = 456
        self.backend.emit([('move', .5, .2), ('up', 'left')])
        self.assertEqual([e[0] for e in self.api.events], [0x0002, 0xC001, 0x0004])
        self.assertEqual(self.backend.held, set())
        self.assertEqual(self.backend.status()['foreground_pid'], 456)

    def test_absolute_coordinates_support_negative_monitor_origin(self):
        self.api.position = (-1900, 100)
        self.backend.emit([('move', -.5, 0)])
        flags, x, y, data = self.api.events[0]
        self.assertEqual(flags, 0xC001)
        self.assertEqual(x, 0)
        self.assertGreater(y, 0)

    def test_click_exactly_down_and_up(self):
        self.backend.emit([('click', 'left')])
        self.assertEqual([e[0] for e in self.api.events], [2, 4])

    def test_scroll_signed_wheel_delta(self):
        self.backend.emit([('scroll', -2), ('scroll', 1)])
        self.assertEqual([e[3] for e in self.api.events], [(-240) & 0xFFFFFFFF, 120])

    def test_delivery_rejection_is_visible_and_cleanup_remains_possible(self):
        self.api.accept = False
        with self.assertRaises(InputDeliveryError):
            self.backend.emit([('down', 'left')])
        self.assertEqual(self.driver.last_status, 'rejected')
        self.assertEqual(self.backend.held, {'left'})
        self.api.accept = True
        self.backend.release_all()
        self.assertEqual(self.backend.held, set())

    def test_failsafe_does_not_block_owned_button_release(self):
        self.backend.emit([('down', 'left')])
        self.api.position = (-1920, 0)
        self.driver.FAILSAFE = True
        with self.assertRaises(InputDeliveryError):
            self.backend.emit([('move', 1, 0)])
        self.backend.release_all()
        self.assertEqual(self.backend.held, set())
        self.assertTrue(self.driver.FAILSAFE)

    def test_simulated_factory_never_loads_native_driver(self):
        with patch('wininput.WindowsMouse', side_effect=AssertionError('real input forbidden')):
            self.assertIsInstance(create_backend(Config(), live=False), SimulatedBackend)


class DesktopControlTests(unittest.TestCase):
    def test_global_hotkeys_do_not_repeat_while_held(self):
        down = set()
        hotkeys = GlobalHotkeys(lambda code: 0x8000 if code in down else 0)
        down.add(0x77)
        self.assertEqual(hotkeys.poll(), [ord(' ')])
        self.assertEqual(hotkeys.poll(), [])
        down.clear(); hotkeys.poll(); down.add(0x77)
        self.assertEqual(hotkeys.poll(), [ord(' ')])
        down.add(0x78)
        self.assertEqual(hotkeys.poll(), [ord('q')])

    def test_blocked_preview_does_not_prevent_drag_or_release(self):
        with patch('window._preview_worker', blocked_preview):
            window = PreviewWindow()
        try:
            controller = Controller(Config())
            backend = SimulatedBackend()
            for t in range(0, 1500, 20):
                gesture = Gesture.OPEN if t < 300 or t >= 1200 else Gesture.LEFT
                x = max(0, min(t-800, 400)) * .0001
                backend.emit(controller.update(hand(gesture, x=x), t))
                window.publish(b'preview')
            self.assertIn(('down', 'left'), backend.events)
            self.assertIn(('up', 'left'), backend.events)
            self.assertTrue(any(e[0] == 'move' for e in backend.events))
            self.assertEqual(backend.held, set())
            self.assertTrue(window.process.is_alive())
        finally:
            window.close()
        self.assertFalse(window.process.is_alive())

    def test_controller_reports_reason_for_stopping(self):
        c = Controller(Config())
        c.update(None, 0)
        self.assertEqual(c.reason, 'no_hand')
        c.update(hand(Gesture.FIST), 20)
        self.assertEqual(c.reason, 'pause_gesture')
        c.enabled = False
        c.update(hand(Gesture.OPEN), 40)
        self.assertEqual(c.reason, 'disabled')


if __name__ == '__main__':
    unittest.main()
