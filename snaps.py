"""Local detection of two short, bright acoustic impulses."""
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import monotonic, sleep

import numpy as np

MAX_PAIR_GAP = 1.05
MIN_INPUT_SIGNAL = .0001
MICROPHONE_MODES = ('default', 'raw', 'communications')


def microphone_info(sd, device, mode):
    info = sd.query_devices(device, 'input')
    host = sd.query_hostapis(info['hostapi'])['name']
    if mode != 'default' and host != 'Windows WASAPI' and device is None:
        matching = (item for item in sd.query_devices()
                    if item['name'] == info['name'] and item['max_input_channels'] > 0
                    and sd.query_hostapis(item['hostapi'])['name'] == 'Windows WASAPI')
        info = next(matching, info)
        host = sd.query_hostapis(info['hostapi'])['name']
    if mode != 'default' and host != 'Windows WASAPI':
        raise ValueError('Este modo requer uma entrada Windows WASAPI. Escolhe o indice com --microphone.')
    return info, host


def microphone_settings(sd, mode):
    if mode == 'default':
        return None
    settings = sd.WasapiSettings()
    # python-sounddevice exposes the PortAudio structure but its constructor
    # does not expose these fields. They affect only this shared capture stream.
    stream_info = getattr(settings, '_streaminfo', None)
    if not all(hasattr(stream_info, field) for field in ('streamOption', 'streamCategory')):
        raise ValueError('Esta versao de sounddevice nao disponibiliza modos WASAPI adicionais.')
    if mode == 'raw':
        stream_info.streamOption = 1  # eStreamOptionRaw
    elif mode == 'communications':
        stream_info.streamCategory = 3  # eAudioCategoryCommunications
    else:
        raise ValueError(f'Modo de microfone desconhecido: {mode}')
    return settings


class SnapPair:
    def __init__(self, sample_rate, sensitivity=1.0):
        self.sample_rate = sample_rate
        self.sensitivity = sensitivity
        self.reset()

    def reset(self):
        self.elapsed = 0.
        self.noise = .0015
        self.onset = None
        self.bright = False
        self.first = None
        self.cooldown_until = 0.
        self.status = 'a ouvir'
        self.status_count = 0
        self.gate = .012 / self.sensitivity

    def report(self, status):
        self.status = status
        self.status_count += 1

    def feed(self, samples):
        """Consume a mono block of about 10 ms and report a completed pair."""
        duration = len(samples) / self.sample_rate
        t = self.elapsed
        self.elapsed += duration
        peak = float(np.max(np.abs(samples)))
        rms = float(np.sqrt(np.mean(samples**2)))
        self.gate = max(.012, self.noise*7) / self.sensitivity
        loud = peak >= self.gate and rms >= self.noise*2.4
        target_noise = min(rms, self.noise*2, .025)
        self.noise += .08 * (target_noise-self.noise)
        if self.first is not None and t-self.first > MAX_PAIR_GAP+.11 and self.onset is None:
            self.first = None
            self.report('segundo estalo nao chegou a tempo')
        if loud:
            if self.onset is None:
                self.onset = t
            if not self.bright and t-self.onset < .065:
                # Tapering prevents abrupt block boundaries from making bass sound sharp.
                power = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))**2
                energy = power[1:].sum()
                upper = int(np.ceil(len(samples) * 1200 / self.sample_rate))
                self.bright = bool(energy and power[upper:].sum() > .16*energy
                                   and power[1:].max() < .42*energy)
            return False
        if self.onset is None:
            return False
        start, bright = self.onset, self.bright
        self.onset, self.bright = None, False
        if start < self.cooldown_until:
            return False
        if t-start > .11:
            self.report('ignorado: som longo')
            return False
        if not bright:
            self.report('ignorado: som sem ataque agudo')
            return False
        if self.first is None or start-self.first > MAX_PAIR_GAP:
            self.first = start
            self.report('primeiro estalo reconhecido')
            return False
        if start-self.first < .14:
            return False  # ringing or echo from the first snap
        self.first = None
        self.cooldown_until = t + .85
        self.report('dois estalos reconhecidos')
        return True


class SnapListener:
    def __init__(self, device=None, sensitivity=1.0, mode='default'):
        import sounddevice as sd

        try:
            info, self.host_name = microphone_info(sd, device, mode)
        except sd.PortAudioError as error:
            raise RuntimeError(f'Microfone indisponivel: {error}') from error
        self.device_name = info['name']
        self.device_index = info['index']
        self.mode = mode
        self.extra_settings = microphone_settings(sd, mode)
        rate = info['default_samplerate']
        if rate < 8000:
            raise ValueError('Microphone sample rate must be at least 8 kHz')
        self.detector = SnapPair(rate, sensitivity)
        self.blocks = Queue(maxsize=16)
        self.discontinuity = Event()
        self.interruptions = 0
        self.toggles = Queue(maxsize=1)
        self.stopped = Event()
        # Several Windows endpoints expose two channels with signal on only one.
        self.channels = min(2, info['max_input_channels'])
        try:
            try:
                self.stream = self._open_stream(sd, rate)
            except sd.PortAudioError:
                if self.channels == 1:
                    raise
                self.channels = 1
                self.stream = self._open_stream(sd, rate)
        except sd.PortAudioError as error:
            raise RuntimeError(f'Nao foi possivel iniciar o microfone {self.device_name}: {error}') from error
        self.signal_started = monotonic()
        self.last_signal = None
        self.channel_peaks = (0.,) * self.channels
        self.max_signal = 0.
        self.processed_frames = 0
        self.worker = Thread(target=self._detect, name='SnapDetector', daemon=True)
        self.worker.start()

    def _open_stream(self, sd, rate):
        stream = sd.InputStream(device=self.device_index, channels=self.channels, dtype='float32',
                                samplerate=rate, blocksize=round(rate/100), callback=self._capture,
                                extra_settings=self.extra_settings)
        try:
            stream.start()
        except sd.PortAudioError:
            stream.close()
            raise
        return stream

    @property
    def description(self):
        return (f'{self.device_name} [{self.device_index}, {self.host_name}, '
                f'{self.channels} canal(is), modo {self.mode}]')

    def _capture(self, data, frames, timestamp, status):
        if status:
            self.discontinuity.set()
        try:
            self.blocks.put_nowait(data.copy())
        except Full:
            self.discontinuity.set()

    def _detect(self):
        while not self.stopped.is_set():
            try:
                block = self.blocks.get(timeout=.1)
            except Empty:
                continue
            if self.discontinuity.is_set():
                self.discontinuity.clear()
                self.interruptions += 1
                self.detector.reset()
                while True:
                    try:
                        self.blocks.get_nowait()
                    except Empty:
                        break
                continue
            if self._feed_block(block):
                try:
                    self.toggles.put_nowait(monotonic())
                except Full:
                    pass

    def _feed_block(self, block):
        peaks = np.max(np.abs(block), axis=0)
        self.channel_peaks = tuple(max(float(peak), previous * .98)
                                   for peak, previous in zip(peaks, self.channel_peaks))
        self.processed_frames += len(block)
        channel = int(np.argmax(peaks))
        self.max_signal = max(self.max_signal, float(peaks[channel]))
        if peaks[channel] > MIN_INPUT_SIGNAL:
            self.last_signal = monotonic()
        # Selecting a channel preserves an impulse that averaging could attenuate.
        return self.detector.feed(block[:, channel])

    def poll(self):
        try:
            return monotonic() - self.toggles.get_nowait() <= 1.
        except Empty:
            return False

    def meter(self):
        detector = self.detector
        levels = '/'.join(f'{peak:.5f}' for peak in self.channel_peaks)
        status = detector.status
        reference = self.last_signal if self.last_signal is not None else self.signal_started
        if monotonic() - reference >= 2.:
            status = 'sem sinal util' if self.processed_frames else 'sem amostras'
        return f'canais {levels} | limiar {detector.gate:.4f} | {status} | interrupcoes {self.interruptions}'

    def close(self):
        self.stopped.set()
        try:
            self.stream.close()
        finally:
            self.worker.join(timeout=1)


def test_microphone(device, sensitivity, mode='default'):
    listener = SnapListener(device, sensitivity, mode)
    try:
        print(f'Microfone: {listener.description}')
        print('Faz pares de estalos. Ctrl+C encerra. A camera fica livre.', flush=True)
        next_meter = 0.
        status = None
        while listener.stream.active and listener.worker.is_alive():
            now = monotonic()
            current = (listener.interruptions, listener.detector.status_count)
            pulse = listener.poll()
            if pulse or current != status or now >= next_meter:
                print(listener.meter() + (' | PAR CONFIRMADO' if pulse else ''), flush=True)
                status, next_meter = current, now + 1.
            sleep(.05)
        raise RuntimeError('O microfone deixou de enviar audio')
    except KeyboardInterrupt:
        pass
    finally:
        listener.close()


def compare_microphone_modes(device, sensitivity):
    """Measure levels on short, consecutive capture streams. No audio is saved."""
    print('Fala continuamente durante os testes. A camera fica livre. Ctrl+C cancela.', flush=True)
    choices = []
    try:
        for mode in MICROPHONE_MODES:
            try:
                listener = SnapListener(device, sensitivity, mode)
            except (ValueError, RuntimeError) as error:
                print(f'{mode}: {error}', flush=True)
                continue
            try:
                print(f'A ouvir por 3 segundos: {listener.description}', flush=True)
                sleep(3)
                peak = listener.max_signal
                if peak > MIN_INPUT_SIGNAL:
                    choices.append((peak, listener.device_index, mode))
                print(f'  Pico {peak:.5f} | {listener.processed_frames} amostras por canal', flush=True)
            finally:
                listener.close()
    except KeyboardInterrupt:
        return
    if choices:
        _, index, mode = max(choices)
        print(f'Maior sinal: --microphone {index} --microphone-mode {mode}', flush=True)
    else:
        print('Nenhum modo recebeu sinal acima do nivel residual.', flush=True)
