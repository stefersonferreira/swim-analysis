"""Eventos automáticos a partir da trajetória e da espuma (módulos 7 e 8, versão clássica).

Gera os mesmos eventos que a marcação manual, com source=auto e uma confiança:
- start_signal: pelo áudio (start_signal.py);
- entry: primeiro respingo forte entre 1,5 m e 7 m depois da largada;
- wall_feet / wall_hands / finish_touch: extremos da trajetória junto às paredes;
- breakout: início da espuma ritmada à frente do nadador depois da fase submersa;
- stroke: picos da espuma à frente do nadador durante o nado;
- mark_pass: passagem da cabeça por 5, 10, 15 e 20 m de cada piscina.

pés fora do bloco continua manual (precisa de pose; entra com o modelo de pose).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from swimcv.contracts import Event, EventSource, EventType, RaceInfo, Stroke
from swimcv.tracking.lane import LaneSignals, Trajectory

E = EventType
MARKS_M = (5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0)
BREAKOUT_LEAD_S = 0.15  # breakout vem um pouco antes do primeiro respingo de braço


@dataclass
class AutoResult:
    events: list[Event]
    notes: list[str]


def _nearest(pts: np.ndarray, t: float) -> int:
    i = int(np.searchsorted(pts, t))
    if i <= 0:
        return 0
    if i >= len(pts):
        return len(pts) - 1
    return i if pts[i] - t < t - pts[i - 1] else i - 1


def _smooth(x: np.ndarray, k: int) -> np.ndarray:
    if k <= 1:
        return x
    return np.convolve(np.pad(x, k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), "same")[k:-k]


def _rolling_median(x: np.ndarray, k: int) -> np.ndarray:
    pad = np.pad(x, k, mode="edge")
    return np.array([np.median(pad[i : i + 2 * k + 1]) for i in range(len(x))])


def _peaks(x: np.ndarray, min_dist: int, height: float) -> list[int]:
    cand = [
        i for i in range(1, len(x) - 1) if x[i] >= x[i - 1] and x[i] > x[i + 1] and x[i] > height
    ]
    cand.sort(key=lambda i: -x[i])
    chosen: list[int] = []
    for i in cand:
        if all(abs(i - j) >= min_dist for j in chosen):
            chosen.append(i)
    return sorted(chosen)


def _cross_time(pts: np.ndarray, d: np.ndarray, level: float, i0: int, i1: int) -> float | None:
    """Primeiro instante em [i0, i1) em que a série d passa a ser >= level (interpolado)."""
    for i in range(max(i0, 1), i1):
        if d[i - 1] < level <= d[i]:
            f = (level - d[i - 1]) / (d[i] - d[i - 1])
            return float(pts[i - 1] + f * (pts[i] - pts[i - 1]))
    return None


def _touch_time(pts: np.ndarray, dist: np.ndarray, L: float, i0: int, i1: int) -> float | None:
    """Toque na parede por extrapolação: a cabeça some na espuma perto da parede, então
    usamos a velocidade entre 6 m e 2 m da parede e projetamos os 2 m restantes."""
    t6 = _cross_time(pts, dist, L - 6.0, i0, i1)
    t2 = _cross_time(pts, dist, L - 2.0, i0, i1)
    if t6 is None or t2 is None or t2 <= t6:
        return None
    v = 4.0 / (t2 - t6)
    return t2 + 2.0 / v


def _fill_gaps(peaks: list[int], pts: np.ndarray) -> tuple[list[int], list[int]]:
    """Braçadas são ritmadas: um intervalo ~2x a mediana indica braçada perdida no meio."""
    if len(peaks) < 4:
        return peaks, []
    gaps = np.diff(pts[peaks])
    med = float(np.median(gaps))
    out, added = [peaks[0]], []
    for a, b, g in zip(peaks[:-1], peaks[1:], gaps, strict=True):
        k = int(round(g / med))
        if k >= 2 and abs(g / k - med) < 0.25 * med:
            for j in range(1, k):
                tj = pts[a] + j * g / k
                i = int(np.argmin(np.abs(pts - tj)))
                out.append(i)
                added.append(i)
        out.append(b)
    return out, added


def generate(
    race: RaceInfo,
    traj: Trajectory,
    sig: LaneSignals,
    start_t: float | None,
    start_conf: float = 0.0,
) -> AutoResult:
    pts = traj.t
    n = len(pts)
    fps = 1.0 / float(np.median(np.diff(pts))) if n > 1 else 30.0
    L = race.pool_length_m
    evs: list[Event] = []
    notes: list[str] = []

    def add(
        kind: EventType, t: float, conf: float, x: float | None = None, mark: float | None = None
    ) -> Event:
        i = _nearest(pts, t)
        ev = Event(
            type=kind,
            frame=i,
            t=float(t),
            x_m=x,
            mark_m=mark,
            confidence=float(np.clip(conf, 0, 1)),
            source=EventSource.AUTO,
        )
        evs.append(ev)
        return ev

    t_begin = 0.0
    if start_t is not None:
        add(E.START_SIGNAL, start_t, start_conf)
        t_begin = start_t
    else:
        notes.append("Sinal de largada não encontrado no áudio: marque com a tecla I.")

    # ---- Entrada na água -----------------------------------------------------------
    i_begin = _nearest(pts, t_begin)
    entry_cols = (sig.xs >= 1.5) & (sig.xs <= 7.0)
    splash = sig.white[:, entry_cols].max(axis=1) if entry_cols.any() else np.zeros(n)
    entry_i = None
    for i in range(i_begin, min(n, i_begin + int(4 * fps))):
        if splash[i] > 0.25:
            entry_i = i
            break
    if entry_i is not None:
        col = sig.xs[entry_cols][int(sig.white[entry_i, entry_cols].argmax())]
        add(E.ENTRY, float(pts[entry_i]), 0.6, x=float(col))
        t_len0 = float(pts[entry_i])
    else:
        notes.append("Entrada na água não detectada.")
        t_len0 = t_begin

    # ---- Piscinas: cruzamentos do meio e viradas -------------------------------------
    body = traj.body_x
    conf = traj.confidence
    half = L / 2
    i0 = _nearest(pts, t_len0)
    crossings = [i for i in range(max(i0, 1), n) if (body[i - 1] - half) * (body[i] - half) < 0]
    # remove cruzamentos espúrios muito próximos (oscilação perto do meio)
    clean: list[int] = []
    for i in crossings:
        if not clean or pts[i] - pts[clean[-1]] > 3.0:
            clean.append(i)
    crossings = clean[: race.n_lengths]
    if len(crossings) < race.n_lengths:
        notes.append(f"Trajetória cobre {len(crossings)} de {race.n_lengths} piscinas.")

    length_start = [t_len0]
    length_end: list[float | None] = []
    for k in range(race.n_lengths - 1):
        if k + 1 >= len(crossings):
            length_end.append(None)
            break
        a, b = crossings[k], crossings[k + 1]
        wall = L if k % 2 == 0 else 0.0
        seg = body[a:b] if wall == L else -body[a:b]
        j = a + int(np.argmax(seg))
        t_feet = float(pts[j])
        c = float(np.mean(conf[max(a, j - 5) : j + 5]))
        if race.stroke == Stroke.BREASTSTROKE:
            head = traj.head_x if wall == L else L - traj.head_x
            t_hands = _touch_time(pts, head, L, a - int(3 * fps), j + 1) or t_feet - 0.6
            add(E.WALL_HANDS, t_hands, 0.5 * c, x=wall)
            add(E.WALL_FEET, max(t_feet, t_hands + 0.2), 0.5 * c, x=wall)
            length_end.append(t_hands)
        else:
            add(E.WALL_FEET, t_feet, 0.6 * c, x=wall)
            length_end.append(t_feet)
        length_start.append(t_feet)

    # chegada
    k_last = race.n_lengths - 1
    if len(length_end) == k_last and len(crossings) > k_last:
        wall = L if k_last % 2 == 0 else 0.0
        head = traj.head_x if wall == L else L - traj.head_x
        t_fin = _touch_time(pts, head, L, crossings[k_last] - int(3 * fps), n)
        if t_fin is not None:
            add(E.FINISH_TOUCH, t_fin, 0.5, x=wall)
            length_end.append(t_fin)
        else:
            length_end.append(None)
            notes.append("Toque final não detectado: use o tempo oficial ou marque com F.")
    while len(length_end) < race.n_lengths:
        length_end.append(None)

    # ---- Por piscina: marcas, breakout, braçadas ---------------------------------------
    fw = _smooth(traj.front_white, 1)
    base = _rolling_median(fw, int(fps))
    act = np.clip(fw - base, 0, None)
    swim_ref = float(np.percentile(act[act > 0], 90)) if (act > 0).any() else 0.0
    min_gap_s = 0.25 if race.stroke == Stroke.FREESTYLE else 0.6
    for k in range(min(race.n_lengths, len(length_start))):
        ts = length_start[k]
        te = length_end[k] if length_end[k] is not None else float(pts[-1])
        ia, ib = _nearest(pts, ts), _nearest(pts, te)
        if ib <= ia + 5:
            continue
        push = 0.0 if k % 2 == 0 else L
        dist = np.abs(traj.head_x - push)
        # marcas de distância (a partir da parede de impulsão)
        for mk in MARKS_M:
            if mk >= L:
                break
            tm = _cross_time(pts, dist, mk, ia, ib + 1)
            if tm is not None:
                c = float(np.mean(conf[max(0, _nearest(pts, tm) - 3) : _nearest(pts, tm) + 4]))
                if c > 0.4:
                    add(E.MARK_PASS, tm, c, mark=mk)
        # nado: do primeiro respingo ritmado até pouco antes do toque/virada
        i_far = _nearest(pts, te - 0.25)
        thr = max(0.015, 0.2 * swim_ref)
        search_from = ia + int(0.6 * fps)
        pk = _peaks(act[search_from:i_far], int(min_gap_s * fps), thr)
        pk = [p + search_from for p in pk]
        # breakout: primeiro pico forte seguido de outro forte em até 1,5 s (nado ritmado);
        # limiar mais alto que o das braçadas para não confundir com respingo da submersa
        strong = [p for p in pk if act[p] > max(0.03, 0.35 * swim_ref)]
        first = next(
            (p for q, p in enumerate(strong[:-1]) if pts[strong[q + 1]] - pts[p] < 1.5), None
        )
        if first is not None:
            tb = float(pts[first]) - BREAKOUT_LEAD_S
            ib_ = _nearest(pts, tb)
            add(E.BREAKOUT, tb, 0.5 * float(conf[ib_]), x=float(traj.head_x[ib_]))
            pk, filled = _fill_gaps([p for p in pk if p >= first], pts)
            for p in pk:
                c = (0.3 if p in filled else 0.6) * float(conf[p])
                add(E.STROKE, float(pts[p]), c, x=float(traj.head_x[p]))
        else:
            notes.append(f"Piscina {k + 1}: braçadas não detectadas.")
    notes.append("Pés fora do bloco: marque com a tecla O para medir a reação.")
    evs.sort(key=lambda e: e.t)
    return AutoResult(events=evs, notes=notes)
