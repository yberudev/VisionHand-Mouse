"""Shape and spectrum of a brief sound. Calibration stores only these numbers."""
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np


# Comparable feature distances for duration, bass, midrange, tonal peaks and tail.
FEATURE_SCALES = np.array([5., .18, .20, .13, .17])


def signature(samples, rate):
    signal = samples - np.mean(samples)
    energy = np.square(signal)
    total = energy.sum()
    if total <= 0:
        return None
    cumulative = np.cumsum(energy)
    early, late = np.searchsorted(cumulative, total * np.array([.05, .95]))
    width_ms = (late - early + 1) * 1000 / rate
    attack = int(np.argmax(energy))
    after_attack = attack + round(rate * .008)
    tail = energy[after_attack:].sum() / total

    # The attack's spectrum is more informative than the room reverberation.
    start = max(0, attack - round(rate * .004))
    stop = min(len(signal), attack + round(rate * .010))
    power = np.abs(np.fft.rfft(signal[start:stop])) ** 2
    frequencies = np.fft.rfftfreq(stop - start, 1 / rate)
    spectral_energy = power[1:].sum()
    if spectral_energy <= 0:
        return None
    bass = power[(frequencies > 0) & (frequencies < 950)].sum() / spectral_energy
    mid = power[(frequencies >= 950) & (frequencies < 9000)].sum() / spectral_energy
    tonality = power[1:].max() / spectral_energy
    return np.array([width_ms, bass, mid, tonality, tail])


def plausible_snap(features):
    width, bass, mid, tone, tail = features
    return .18 <= width <= 22 and bass <= .62 and mid >= .14 and tone <= .36 and tail <= .32


def distance(left, right):
    return float(np.sqrt(np.mean(np.square((left - right) / FEATURE_SCALES))))


@dataclass
class SnapProfile:
    positive: list
    negative: list

    def accepts(self, features):
        if not .18 <= features[0] <= 38:
            return False
        closest_snap = min(distance(features, example) for example in self.positive)
        closest_noise = min((distance(features, example) for example in self.negative), default=float('inf'))
        return closest_snap <= 1.25 and closest_snap + .18 < closest_noise

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('version') != 1:
            raise ValueError('Formato do perfil de estalos desconhecido')

        def examples(key, minimum):
            vectors = np.asarray(data.get(key, []), dtype=float)
            if not vectors.size and not minimum:
                return []
            if vectors.ndim != 2 or vectors.shape[1] != len(FEATURE_SCALES):
                raise ValueError('Perfil de estalos com formato invalido')
            if not minimum <= len(vectors) <= 32 or not np.isfinite(vectors).all():
                raise ValueError('Perfil de estalos com exemplos invalidos')
            return list(vectors)

        return cls(examples('snaps', 3), examples('noise', 0))

    def save(self, path):
        content = dict(version=1, snaps=[v.tolist() for v in self.positive],
                       noise=[v.tolist() for v in self.negative])
        target = Path(path)
        pending = target.with_suffix(target.suffix + '.tmp')
        pending.write_text(json.dumps(content, indent=2) + '\n', encoding='utf-8')
        pending.replace(target)
