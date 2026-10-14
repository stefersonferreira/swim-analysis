"""Largada automática pelo áudio (módulo 7, parte 1).

Em competição, a largada é um tom eletrônico (bipe ou buzina) curto depois de apitos longos do
árbitro e de alguns segundos de relativo silêncio ("às suas marcas"). Em treino, costuma ser um
apito longo ("subam") e depois um apito curto. Nos dois casos a largada é o último sinal forte
da sequência (order_candidates). A pontuação de cada candidato combina:

- subida brusca de energia na faixa 500–4.000 Hz;
- tonalidade (espectro concentrado num pico que varia de forma contínua, não ruído de torcida;
  o apito de treino "trina" e desliza entre ~2,5 e 4 kHz, o bipe fica parado);
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
STRONG_FRACTION = 0.6
SEQUENCE_GAP_S = 6.0
GAP_FILL_S = 0.04  # buracos curtos dentro de um mesmo apito (trinado)
MAX_GLIDE_HZ = 150.0  # variação típica do pico entre janelas vizinhas (5 ms)


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


def refine_onset(x: np.ndarray, rate: int, t0: float, freq: float, half_bw: float = 150.0) -> float:
    """Início exato do tom: envelope do sinal filtrado em torno da frequência do tom,
    primeiro instante acima de metade do pico (precisão de ~1 ms)."""
    a = max(0, int((t0 - 0.12) * rate))
    b = min(len(x), int((t0 + 0.20) * rate))
    seg = x[a:b]
    if len(seg) < 64:
        return max(0.0, t0)
    spec = np.fft.fft(seg)
    f = np.fft.fftfreq(len(seg), 1.0 / rate)
    # analítico (só frequências positivas) e passa-faixa em torno do tom (±150 Hz num bipe;
    # a faixa toda num apito que desliza)
    keep = (f > 0) & (np.abs(f - freq) < half_bw)
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
    # tonalidade suavizada (~25 ms): o trinado do apito derruba quadros isolados
    k = max(1, int(0.025 / dt))
    tonal_s = np.convolve(tonal, np.ones(k) / k, mode="same")
    active = (rise > 12.0) & (tonal_s > 0.3)
    # junta trechos separados por buracos curtos
    gap = max(1, int(GAP_FILL_S / dt))
    runs = _runs(active)
    for (_, b0), (a1, _) in zip(runs, runs[1:], strict=False):
        if a1 - b0 <= gap:
            active[b0:a1] = True

    cands: list[StartCandidate] = []
    for a, b in _runs(active):
        dur = (b - a) * dt
        if dur < 0.08 or dur > 1.5:
            continue
        f = float(np.median(peak_hz[a:b]))
        # o pico pode deslizar (apito), mas aos saltos é ruído (torcida, água)
        glide = float(np.median(np.abs(np.diff(peak_hz[a:b])))) if b - a > 1 else 0.0
        if glide > MAX_GLIDE_HZ:
            continue
        quiet = float(np.median(rise[max(0, a - w) : a])) if a > 0 else 0.0
        r = float(np.percentile(rise[a:b], 80))
        score = r * float(np.mean(tonal_s[a:b])) - 0.5 * max(quiet, 0.0)
        # tons longos (> 0,6 s) costumam ser o apito de "subam no bloco", não a largada
        if dur > 0.6:
            score *= 0.6
        # o início exato: primeiro quadro de STFT acima de metade da subida
        onset = a
        while onset > 0 and rise[onset - 1] > r / 2:
            onset -= 1
        coarse = onset * dt + (WIN / 2) / rate  # centro da janela STFT
        spread = float(np.percentile(peak_hz[a:b], 90) - np.percentile(peak_hz[a:b], 10))
        if spread > 300.0:  # apito: o tom desliza, mede o início na faixa inteira
            lo, hi = BAND_HZ
            t = refine_onset(x, rate, coarse, (lo + hi) / 2, (hi - lo) / 2)
        else:
            t = refine_onset(x, rate, coarse, f)
        cands.append(StartCandidate(t=t, score=score, duration_s=dur, freq_hz=f, rise_db=r))
    return order_candidates(cands)[:top]


def order_candidates(cands: list[StartCandidate]) -> list[StartCandidate]:
    """Põe primeiro o sinal que vale como largada.

    A largada é o último sinal da sequência de saída: numa competição, apitos longos do árbitro
    e depois o bipe; num treino, apito longo ("subam") e depois o apito curto ou a voz de saída.
    A sequência começa no sinal mais forte e segue pelos sinais fortes (pelo menos
    STRONG_FRACTION da melhor pontuação) que vêm a no máximo SEQUENCE_GAP_S do anterior. Gritos
    no meio da prova, bem depois, ficam de fora. Os demais seguem por pontuação.
    """
    if not cands:
        return []
    best = max(cands, key=lambda c: c.score)
    chosen = best
    if best.score > 0:
        strong = sorted(
            (c for c in cands if c.score >= STRONG_FRACTION * best.score and c.t > best.t),
            key=lambda c: c.t,
        )
        for c in strong:
            if c.t - chosen.t > SEQUENCE_GAP_S:
                break
            chosen = c
    rest = sorted((c for c in cands if c is not chosen), key=lambda c: c.score, reverse=True)
    return [chosen, *rest]


def detect_start(wav_path: Path) -> list[StartCandidate]:
    if not Path(wav_path).exists():
        return []
    x, rate = read_wav(wav_path)
    return find_start_candidates(x, rate)


def confidence(cands: list[StartCandidate]) -> float:
    """Confiança 0..1 do candidato escolhido (o primeiro da lista).

    Alta quando ele é o único sinal forte; média quando houve vários sinais fortes e a escolha
    foi pela ordem (último da sequência), o que pede conferência mas não é dúvida grave.
    """
    if not cands:
        return 0.0
    chosen = cands[0]
    best = max(c.score for c in cands)
    if best <= 0:
        return 0.2
    others = [c.score for c in cands[1:]]
    second = max(others) if others else 0.0
    if second < STRONG_FRACTION * best:
        margin = (chosen.score - second) / chosen.score
        return float(np.clip(0.5 + 0.5 * margin, 0.0, 0.99))
    return float(np.clip(0.45 + 0.2 * chosen.score / best, 0.0, 0.8))
