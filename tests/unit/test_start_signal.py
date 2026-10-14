import numpy as np
import pytest

from swimcv.events.start_signal import confidence, find_start_candidates

RATE = 48_000


def tone(f, dur, amp=0.5, rate=RATE):
    t = np.arange(int(dur * rate)) / rate
    return amp * np.sin(2 * np.pi * f * t)


def pool_audio(beep_at=6.0, seed=0, whistle=True, beep_f=1200.0, beep_dur=0.25):
    """Ruído de piscina (torcida) + apito longo do árbitro + silêncio + bipe + torcida."""
    rng = np.random.default_rng(seed)
    n = int(12 * RATE)
    noise = rng.normal(0, 1, n)
    # ruído rosa aproximado: filtra o branco
    noise = np.convolve(noise, np.ones(30) / 30, mode="same") * 0.15
    x = noise.copy()
    # silêncio relativo antes da largada
    a, b = int((beep_at - 2.0) * RATE), int(beep_at * RATE)
    x[a:b] *= 0.25
    if whistle:
        w = tone(3400, 1.2, 0.4) * np.linspace(0.6, 1, int(1.2 * RATE))
        s = int(1.0 * RATE)
        x[s : s + len(w)] += w + 0.05 * np.sin(np.linspace(0, 60, len(w)))
    bp = tone(beep_f, beep_dur, 0.6)
    s = int(beep_at * RATE)
    x[s : s + len(bp)] += bp
    # torcida depois da largada
    x[s + len(bp) :] += rng.normal(0, 0.2, n - s - len(bp))
    return x.astype(np.float32)


@pytest.mark.parametrize("beep_at", [3.0, 6.0, 9.4])
def test_finds_beep_not_whistle(beep_at):
    cands = find_start_candidates(pool_audio(beep_at=beep_at), RATE)
    assert cands, "nenhum candidato"
    assert cands[0].t == pytest.approx(beep_at, abs=0.012)  # menos de meio quadro a 60 fps
    assert 1100 < cands[0].freq_hz < 1300
    assert confidence(cands) > 0.5


def test_horn_style_start():
    x = pool_audio(beep_at=4.0, beep_f=650.0, beep_dur=0.6, whistle=False)
    cands = find_start_candidates(x, RATE)
    assert cands[0].t == pytest.approx(4.0, abs=0.012)


def test_silence_gives_nothing():
    assert find_start_candidates(np.zeros(RATE * 3, np.float32), RATE) == []
    assert confidence([]) == 0.0


def harmonic(f, dur, amp=0.4, rate=RATE):
    """Voz/buzina grave: fundamental com harmônicos."""
    return sum(tone(f * k, dur, amp / k, rate) for k in (1, 2, 3))


def test_training_whistle_start_is_the_last_strong_signal():
    """Treino real (vídeo IMG_6612): apito longo, voz do técnico, apito curto de saída."""
    rng = np.random.default_rng(1)
    x = (np.convolve(rng.normal(0, 1, 20 * RATE), np.ones(30) / 30, "same") * 0.1).astype(
        np.float32
    )
    for at, sig in (
        (2.0, tone(3500, 1.0, 0.5)),
        (4.0, harmonic(650, 0.25)),
        (6.3, tone(3600, 0.5, 0.5)),
        (15.0, harmonic(650, 0.25)),  # técnico gritando no meio da prova
    ):
        s = int(at * RATE)
        x[s : s + len(sig)] += sig
    cands = find_start_candidates(x, RATE)
    assert cands[0].t == pytest.approx(6.3, abs=0.012)
    assert 0.35 < confidence(cands) <= 0.8  # escolha pela ordem: pede conferência


def test_trilled_whistle_right_at_the_start_of_the_video():
    """Treino gravado já com os nadadores no bloco: apito trinado (o tom desliza entre
    2,4 e 3,9 kHz) 1 s depois do início. Antes era descartado por "frequência instável"."""
    rng = np.random.default_rng(3)
    x = (np.convolve(rng.normal(0, 1, 6 * RATE), np.ones(30) / 30, "same") * 0.02).astype(
        np.float32
    )
    dur = 0.3
    t = np.arange(int(dur * RATE)) / RATE
    f = 3150 + 750 * np.sin(2 * np.pi * 9 * t)  # trinado de 9 Hz
    w = 0.5 * np.sin(2 * np.pi * np.cumsum(f) / RATE)
    s = int(1.05 * RATE)
    x[s : s + len(w)] += w.astype(np.float32)
    cands = find_start_candidates(x, RATE)
    assert cands and cands[0].t == pytest.approx(1.05, abs=0.015)
    assert confidence(cands) > 0.8
