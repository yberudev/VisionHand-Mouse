import unittest
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock

try:
    import numpy as np
except ImportError:
    np = None


@unittest.skipIf(np is None, 'NumPy is required by the snap detector')
class SnapTests(unittest.TestCase):
    def test_raw_mode_uses_wasapi_alias_of_default_microphone(self):
        from snaps import microphone_info

        mme = dict(index=1, name='Mic', hostapi=0, max_input_channels=2)
        wasapi = dict(index=9, name='Mic', hostapi=1, max_input_channels=2)
        another = dict(index=8, name='Other', hostapi=1, max_input_channels=2)
        sd = Mock()
        sd.query_devices.side_effect = lambda *args: mme if args else [another, wasapi]
        sd.query_hostapis.side_effect = lambda index: {'name': ('MME', 'Windows WASAPI')[index]}
        self.assertEqual(microphone_info(sd, None, 'raw'), (wasapi, 'Windows WASAPI'))
        with self.assertRaisesRegex(ValueError, 'WASAPI'):
            microphone_info(sd, 1, 'raw')

    def test_capture_modes_set_only_their_portaudio_fields(self):
        from snaps import microphone_settings

        sd = Mock()
        sd.WasapiSettings.side_effect = lambda: SimpleNamespace(
            _streaminfo=SimpleNamespace(streamOption=0, streamCategory=0))
        self.assertIsNone(microphone_settings(sd, 'default'))
        raw = microphone_settings(sd, 'raw')._streaminfo
        voice = microphone_settings(sd, 'communications')._streaminfo
        self.assertEqual((raw.streamOption, raw.streamCategory), (1, 0))
        self.assertEqual((voice.streamOption, voice.streamCategory), (0, 3))

    def make_listener(self):
        from snaps import SnapListener

        listener = SnapListener.__new__(SnapListener)
        listener.detector = Mock(gate=.012, status='a ouvir')
        listener.signal_started = monotonic() - 3
        listener.last_signal = None
        listener.channel_peaks = (0., 0.)
        listener.processed_frames = 0
        listener.max_signal = 0.
        listener.interruptions = 0
        return listener

    def test_second_channel_can_carry_the_snap(self):
        listener = self.make_listener()
        data = np.zeros((441, 2))
        data[200, 1] = .04
        listener.detector.feed.return_value = True
        self.assertTrue(listener._feed_block(data))
        np.testing.assert_array_equal(listener.detector.feed.call_args.args[0], data[:, 1])
        self.assertIn('canais 0.00000/0.04000', listener.meter())

    def test_meter_distinguishes_missing_samples_from_digital_silence(self):
        listener = self.make_listener()
        self.assertIn('sem amostras', listener.meter())
        listener._feed_block(np.full((441, 2), 1/32768))
        self.assertIn('sem sinal util', listener.meter())

    def run_audio(self, onsets, background=None, rate=44100, amplitude=.85, softened=False):
        from snaps import SnapPair

        audio = np.zeros(rate*4, dtype=np.float32) if background is None else background.copy()
        rng = np.random.default_rng(27)
        for time in onsets:
            start = round(time*rate)
            # Short broadband burst with a decaying envelope and mixed signs.
            length = round(rate*.004)
            burst = rng.choice((-1., 1.), length) * np.exp(-np.arange(length)/(rate*.0008))
            if softened:
                burst = np.convolve(burst, np.ones(5)/5, mode='same')
            audio[start:start+length] += amplitude * burst
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
        for onsets in ((.4,), (.4, .47), (.4, 1.6)):
            with self.subTest(onsets=onsets):
                self.assertEqual(self.run_audio(onsets), [])

    def test_quiet_softened_snaps_at_a_slower_cadence(self):
        rate = 44100
        background = np.random.default_rng(42).normal(0., .001, rate*4)
        toggles = self.run_audio((.405, 1.285), background, rate, amplitude=.034, softened=True)
        self.assertEqual(len(toggles), 1)
        self.assertTrue(1.285 < toggles[0] < 1.35)

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
