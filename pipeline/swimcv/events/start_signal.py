"""Largada automática pelo áudio (módulo 7, parte 1).

O sinal eletrônico de largada é um tom (bipe ou buzina) curto que vem depois de alguns
segundos de relativo silêncio ("às suas marcas"). Os apitos do árbitro também são tons, mas
vêm antes e costumam ser longos. A pontuação de cada candidato combina:

- subida brusca de energia na faixa 500–4.000 Hz;
- tonalidade (espectro concentrado num pico estável, não ruído de torcida);
- silêncio relativo no segundo anterior;
- duração plausível (80 ms a 1,5 s).

Só numpy: nada de modelo nem dependência extra.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HOP_S = 0.005
WIN = 2048
BAND_HZ = (500.0, 4000.0)
SEARCH_S = 25.0


@dataclass
class StartCandidate:
    t: float  # início do tom, em segundos do áudio (= tempo do vídeo)
    score: float
    duration_s: float
    freq_hz: float
    rise_db: float


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        n_ch = w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    if n_ch > 1:
        data = data.reshape(-1, n_ch).mean(axis=1)
    return data / 32768.0, rate


def _stft_mag(x: np.ndarray, rate: int) -> tuple[np.ndarray, np.ndarray, float]:
    hop = max(1, int(rate * HOP_S))
    if len(x) < WIN:
        x = np.pad(x, (0, WIN - len(x)))
    n = 1 + (len(x) - WIN) // hop
    idx = np.arange(WIN)[None, :] + hop * np.arange(n)[:, None]
    frames = x[idx] * np.hanning(WIN)[None, :]
    mag = np.abs(np.fft.rfft(frames, axis=1))
    freqs = np.fft.rfftfreq(WIN, 1.0 / rate)
    return mag, freqs, hop / rate


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Trechos contínuos True como (início, fim exclusivo)."""
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1), strict=True))


def refine_onset(x: np.ndarray, rate: int, t0: float, freq: float) -> float:
    """Início exato do tom: envelope do sinal filtrado em torno da frequência do tom,
    primeiro instante acima de metade do pico (precisão de ~1 ms)."""
    a = max(0, int((t0 - 0.12) * rate))
    b = min(len(x), int((t0 + 0.20) * rate))
    seg = x[a:b]
    if len(seg) < 64:
        return max(0.0, t0)
    spec = np.fft.fft(seg)
    f = np.fft.fftfreq(len(seg), 1.0 / rate)
    # analítico (só frequências positivas) e passa-faixa de ±150 Hz em torno do tom
    keep = (f > 0) & (np.abs(f - freq) < 150.0)
    env = np.abs(np.fft.ifft(np.where(keep, 2 * spec, 0)))
    k = max(1, int(0.002 * rate))
    env = np.convolve(env, np.ones(k) / k, mode="same")
    peak = float(np.percentile(env, 99))
    above = np.flatnonzero(env > 0.5 * peak)
    if not above.size:
        return max(0.0, t0)
    return max(0.0, (a + int(above[0])) / rate)


def find_start_candidates(x: np.ndarray, rate: int, top: int = 3) -> list[StartCandidate]:
    x = x[: int(SEARCH_S * rate)]
    if len(x) < rate // 2:
        return []
    mag, freqs, dt = _stft_mag(x, rate)
    band = (freqs >= BAND_HZ[0]) & (freqs <= BAND_HZ[1])
    pb = mag[:, band] ** 2
    band_e = pb.sum(axis=1) + 1e-12
    band_db = 10 * np.log10(band_e)
    # tonalidade: fração da energia da faixa num pico estreito (±3 bins) em torno do máximo
    peak_bin = pb.argmax(axis=1)
    cols = np.arange(pb.shape[1])
    near = np.abs(cols[None, :] - peak_bin[:, None]) <= 3
    tonal = (pb * near).sum(axis=1) / band_e
    peak_hz = freqs[band][peak_bin]

    # nível de fundo: mediana móvel de 1 s, olhando só para trás
    w = max(1, int(1.0 / dt))
    floor_db = np.array(
        [
            np.median(band_db[max(0, i - w) : i]) if i > 0 else band_db[0]
            for i in range(len(band_db))
        ]
    )
    rise = band_db - floor_db
    active = (rise > 12.0) & (tonal > 0.35)

    cands: list[StartCandidate] = []
    for a, b in _runs(active):
        dur = (b - a) * dt
        if dur < 0.08 or dur > 1.5:
            continue
        f = float(np.median(peak_hz[a:b]))
        f_stab = float(np.std(peak_hz[a:b]))
        if f_stab > 120.0:  # tom com frequência instável = não é bipe/buzina
            continue
        quiet = float(np.median(rise[max(0, a - w) : a])) if a > 0 else 0.0
        r = float(np.percentile(rise[a:b], 80))
        score = r * float(np.mean(tonal[a:b])) - 0.5 * max(quiet, 0.0)
        # bipes longos (> 0,6 s) parecem apito de árbitro: penaliza
        if dur > 0.6:
            score *= 0.6
        # o início exato: primeiro quadro de STFT acima de metade da subida
        onset = a
        while onset > 0 and rise[onset - 1] > r / 2:
            onset -= 1
        coarse = onset * dt + (WIN / 2) / rate  # centro da janela STFT
        t = refine_onset(x, rate, coarse, f)
        cands.append(StartCandidate(t=t, score=score, duration_s=dur, freq_hz=f, rise_db=r))
    cands.sort(key=lambda c: c.score, reverse=True)
    return cands[:top]


def detect_start(wav_path: Path) -> list[StartCandidate]:
    if not Path(wav_path).exists():
        return []
    x, rate = read_wav(wav_path)
    return find_start_candidates(x, rate)


def confidence(cands: list[StartCandidate]) -> float:
    """Confiança 0..1: alta quando o melhor candidato se destaca do segundo."""
    if not cands:
        return 0.0
    best = cands[0].score
    if best <= 0:
        return 0.2
    second = cands[1].score if len(cands) > 1 else 0.0
    margin = (best - second) / best
    return float(np.clip(0.5 + 0.5 * margin, 0.0, 0.99))
