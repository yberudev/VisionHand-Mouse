import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from windows_audio import InputStatus, warn_if_default_input_muted


class WindowsAudioTests(unittest.TestCase):
    def test_mute_warning_even_when_recording_volume_is_high(self):
        with patch('windows_audio.default_input_status', return_value=InputStatus(True, .82)):
            output = io.StringIO()
            with redirect_stdout(output):
                warn_if_default_input_muted()
            self.assertIn('silenciada (volume 82%)', output.getvalue())

    def test_unavailable_endpoint_diagnostic_does_not_block_launch(self):
        with patch('windows_audio.default_input_status', side_effect=OSError('No endpoint')):
            warn_if_default_input_muted()
