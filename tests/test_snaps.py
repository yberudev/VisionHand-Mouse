import unittest

try:
    import numpy as np
except ImportError:
    np = None


@unittest.skipIf(np is None, 'NumPy is required by the snap detector')
class SnapTests(unittest.TestCase):
    def run_audio(self, onsets, background=None, rate=44100):
        from snaps import SnapPair

        audio = np.zeros(rate*4, dtype=np.float32) if background is None else background.copy()
        rng = np.random.default_rng(27)
        for time in onsets:
            start = round(time*rate)
            # Short broadband burst with a decaying envelope and mixed signs.
            length = round(rate*.004)
            audio[start:start+length] += .85 * rng.choice((-1., 1.), length) * np.exp(
                -np.arange(length)/(rate*.0008))
        detector = SnapPair(rate)
        block = rate//100
        return [i/rate for i in range(0, len(audio), block)
                if detector.feed(audio[i:i+block])]

    def test_pair_toggles_once_and_can_toggle_again(self):
        for rate in (44100, 48000):
            with self.subTest(rate=rate):
                toggles = self.run_audio((.405, .72, .91, 2.01, 2.4), rate=rate)
                self.assertEqual(len(toggles), 2)
                self.assertTrue(.72 < toggles[0] < .80)
                self.assertTrue(2.4 < toggles[1] < 2.48)

    def test_single_and_out_of_window_snaps_do_not_toggle(self):
        for onsets in ((.4,), (.4, .47), (.4, 1.3)):
            with self.subTest(onsets=onsets):
                self.assertEqual(self.run_audio(onsets), [])

    def test_low_frequency_bursts_and_background_noise_do_not_toggle(self):
        rate = 44100
        audio = np.random.default_rng(42).normal(0., .009, rate*4)
        time = np.arange(rate//5)/rate
        for onset in (.4, .75):
            start = round(onset*rate)
            audio[start:start+len(time)] += .4 * np.sin(2*np.pi*220*time)
        self.assertEqual(self.run_audio((), audio), [])

    def test_long_high_frequency_bursts_do_not_toggle(self):
        rate = 44100
        audio = np.zeros(rate*4)
        for onset in (.4, .73):
            start = round(onset*rate)
            t = np.arange(rate//8)/rate
            audio[start:start+len(t)] = .5*np.sin(2*np.pi*3500*t)
        self.assertEqual(self.run_audio((.4, .73), audio), [])
