"""Linha do tempo da sobreposição (balões, relógio, painel de números).

Uma única função pura monta tudo o que a sobreposição mostra, a partir dos eventos já com
posição, do relatório de métricas e da trajetória (opcional). O navegador desenha a partir
deste JSON (frontend/src/overlay/state.ts) e o MP4 exportado também (render.py usa
state_at daqui). As duas implementações de state_at seguem as mesmas regras; os testes de
cada lado usam os mesmos casos.

Convenções:
- t é o tempo do vídeo (s). O relógio da prova é t - largada, congelado na chegada.
- "race_d" é a distância percorrida na prova (0 até a distância total), não a posição x na
  piscina. Vem da trajetória quando existe; senão, dos eventos com posição.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from swimcv.contracts import Event, EventType, MetricsReport, RaceInfo, Stroke
from swimcv.metrics.compute import split_lengths

E = EventType
CALLOUT_S = 2.6  # tempo que um balão fica na tela
TURN_BEFORE_S = 1.0  # a virada começa um pouco antes do toque
TRACK_STEP_S = 1 / 15  # amostragem da trajetória enviada ao navegador
SPEED_WINDOW_S = 1.0
SUMMARY_TAIL_S = 0.3  # vídeo curto: resumo nos últimos instantes
START_MAX_S = 2.0  # sem entrada nem pés fora marcados, "Saída" some depois disso

STROKE_LABEL = {Stroke.FREESTYLE: "Livre", Stroke.BREASTSTROKE: "Peito"}
PHASE_LABEL = {
    "ready": "Preparação",
    "start": "Saída",
    "underwater": "Submerso",
    "swim": "Nadando",
    "turn": "Virada",
    "finish": "Chegada",
}


def br(v: float, digits: int = 2) -> str:
    return f"{v:.{digits}f}".replace(".", ",")


def clock_text(s: float) -> str:
    """Relógio de prova: 9,87 / 1:02,35."""
    s = max(0.0, s)
    m, r = divmod(s, 60)
    return f"{int(m)}:{r:05.2f}".replace(".", ",") if m >= 1 else br(r)


@dataclass
class TrackSample:
    t: float
    race_d: float
    x: float | None  # cabeça na imagem (px do vídeo), se houver trajetória
    y: float | None


def _first(evs: list[Event], kind: EventType) -> Event | None:
    return next((e for e in evs if e.type == kind), None)


def _metric(report: MetricsReport, name: str, **kw) -> float | None:
    m = report.get(name, **kw)
    return m.value if m is not None and m.value is not None else None


def _race_points(race: RaceInfo, lengths, start: Event | None) -> list[tuple[float, float]]:
    """(t, distância de prova) a partir dos eventos, quando não há trajetória."""
    L = race.pool_length_m
    pts: list[tuple[float, float]] = []
    if start is not None:
        pts.append((start.t, 0.0))
    feet_off = lengths[0].first(E.FEET_OFF)
    if feet_off is not None:
        pts.append((feet_off.t, 0.0))
    for ln in lengths:
        for e in ln.events:
            if e.type == E.MARK_PASS and e.mark_m is not None:
                pts.append((e.t, ln.index * L + e.mark_m))
            elif e.type in (E.WALL_HANDS, E.WALL_FEET, E.FINISH_TOUCH):
                pts.append((e.t, (ln.index + 1) * L))
            elif e.x_m is not None:
                d = e.x_m if ln.index % 2 == 0 else L - e.x_m
                pts.append((e.t, ln.index * L + d))
    pts.sort()
    # distância nunca volta: o toque das mãos e os pés na parede ficam no mesmo ponto
    out: list[tuple[float, float]] = []
    for t, d in pts:
        if out and d < out[-1][1]:
            d = out[-1][1]
        out.append((t, d))
    return out


def _track(race: RaceInfo, lengths, start: Event | None, traj: dict | None) -> list[TrackSample]:
    L = race.pool_length_m
    evpts = _race_points(race, lengths, start)
    if traj is None or len(traj.get("t", [])) == 0:
        return [TrackSample(t, d, None, None) for t, d in evpts]
    t = np.asarray(traj["t"], float)
    head = np.asarray(traj["head_x"], float)
    hx = np.asarray(traj.get("head_img_x", [np.nan] * len(t)), float)
    hy = np.asarray(traj.get("head_img_y", [np.nan] * len(t)), float)
    # piscina de cada instante pelos toques de fechamento
    bounds = [ln.t_end for ln in lengths[:-1] if ln.t_end is not None]
    k = np.searchsorted(np.asarray(bounds, float), t, side="right")
    d = np.where(k % 2 == 0, head, L - head)
    race_d = np.clip(k * L + np.clip(d, 0, L), 0, race.distance)
    t0 = start.t if start is not None else t[0]
    race_d[t < t0] = 0.0
    # antes dos pés saírem do bloco a cabeça ainda está na parede
    feet_off = lengths[0].first(E.FEET_OFF)
    if feet_off is not None:
        race_d[t < feet_off.t] = 0.0
    race_d = np.maximum.accumulate(race_d)
    finish = lengths[-1].first(E.FINISH_TOUCH)
    if finish is not None:
        race_d[t >= finish.t] = race.distance
    step = max(1, int(round(TRACK_STEP_S / max(np.median(np.diff(t)), 1e-3)))) if len(t) > 1 else 1
    idx = list(range(0, len(t), step))
    if idx[-1] != len(t) - 1:
        idx.append(len(t) - 1)
    return [
        TrackSample(
            float(t[i]),
            float(race_d[i]),
            None if np.isnan(hx[i]) else float(hx[i]),
            None if np.isnan(hy[i]) else float(hy[i]),
        )
        for i in idx
    ]


def _speed_series(track: list[TrackSample]) -> list[float | None]:
    """Velocidade de prova (m/s) em janela centrada de ~1 s."""
    if len(track) < 3:
        return [None] * len(track)
    t = np.array([s.t for s in track])
    d = np.array([s.race_d for s in track])
    out: list[float | None] = []
    for i in range(len(track)):
        a = int(np.searchsorted(t, t[i] - SPEED_WINDOW_S / 2))
        b = int(np.searchsorted(t, t[i] + SPEED_WINDOW_S / 2, side="right")) - 1
        dt = t[b] - t[a]
        out.append(round(float((d[b] - d[a]) / dt), 3) if dt > 0.3 else None)
    return out


def build_timeline(
    race: RaceInfo,
    events: list[Event],
    report: MetricsReport,
    *,
    title: str = "",
    athlete: str | None = None,
    width: int = 1920,
    height: int = 1080,
    duration_s: float = 0.0,
    trajectory: dict | None = None,
) -> dict:
    """Tudo o que a sobreposição precisa, em JSON simples.

    trajectory: colunas t, head_x e, opcionalmente, head_img_x/head_img_y (como em
    analysis/trajectory.parquet).
    """
    evs = sorted(events, key=lambda e: (e.t, e.frame))
    L = race.pool_length_m
    start = _first(evs, E.START_SIGNAL)
    lengths = split_lengths(race, evs)
    finish = lengths[-1].first(E.FINISH_TOUCH)
    t0 = start.t if start is not None else None
    closing = E.WALL_FEET if race.stroke == Stroke.FREESTYLE else E.WALL_HANDS
    cycle = race.strokes_per_cycle
    stroke_word = "Braçadas" if race.stroke == Stroke.FREESTYLE else "Ciclos"

    track = _track(race, lengths, start, trajectory)
    speeds = _speed_series(track)

    # ---- fases -------------------------------------------------------------------------
    phases: list[dict] = []

    def phase(kind: str, a: float | None, b: float | None, k: int) -> None:
        if a is None:
            return
        phases.append({"kind": kind, "label": PHASE_LABEL[kind], "t0": a, "t1": b, "length": k})

    feet_off = lengths[0].first(E.FEET_OFF)
    entry = lengths[0].first(E.ENTRY)
    phase("ready", -1e9, t0 if t0 is not None else None, 0)
    start_end = entry.t if entry else (feet_off.t if feet_off else None)
    if start_end is None and t0 is not None:
        start_end = t0 + START_MAX_S  # nada marcado depois da largada: não fingir uma fase
    phase("start", t0, start_end, 0)
    for ln in lengths:
        k = ln.index
        bo = ln.first(E.BREAKOUT)
        sub_from = entry.t if k == 0 and entry else ln.t_start
        if k > 0:
            prev_close = lengths[k - 1].of(E.WALL_FEET)
            sub_from = prev_close[-1].t + 0.0 if prev_close else ln.t_start
        if sub_from is not None and bo is not None:
            phase("underwater", sub_from, bo.t, k)
        swim_from = bo.t if bo else sub_from
        end = ln.t_end
        if k < len(lengths) - 1:
            closes = ln.of(closing)
            wall_t = closes[-1].t if closes else end
            if wall_t is not None:
                phase("swim", swim_from, wall_t - TURN_BEFORE_S, k)
                feet = ln.of(E.WALL_FEET)
                turn_end = feet[-1].t if feet else wall_t
                phase("turn", wall_t - TURN_BEFORE_S, turn_end, k)
            else:
                phase("swim", swim_from, None, k)
        else:
            phase("swim", swim_from, finish.t if finish else None, k)
    if finish is not None:
        phase("finish", finish.t, 1e9, len(lengths) - 1)
    # fases em ordem e sem sobreposição (a seguinte corta a anterior)
    phases = [p for p in phases if p["t0"] is not None]
    phases.sort(key=lambda p: p["t0"])
    for a, b in zip(phases, phases[1:], strict=False):
        if a["t1"] is None or a["t1"] > b["t0"]:
            a["t1"] = b["t0"]
    phases = [p for p in phases if p["t1"] is None or p["t1"] > p["t0"]]

    # ---- piscinas: braçadas com tempo de ciclo corrente ---------------------------------
    out_lengths = []
    for ln in lengths:
        k = ln.index
        st = [e.t for e in ln.of(E.STROKE)]
        tempos: list[float | None] = []
        for i in range(len(st)):
            j = i - cycle
            tempos.append(round(st[i] - st[j], 3) if j >= 0 else None)
        split = _metric(report, "split_s", length_index=k)
        if k == len(lengths) - 1:
            split = _metric(report, "final_time_s", length_index=k)
        out_lengths.append(
            {
                "index": k,
                "t_start": ln.t_start,
                "t_end": ln.t_end,
                "strokes": [[round(t, 3), tp] for t, tp in zip(st, tempos, strict=True)],
                "tempo": _metric(report, "tempo_s_per_cycle", length_index=k),
                "speed": _metric(report, "swim_speed_mps", length_index=k),
                "dpc": _metric(report, "dpc_m", length_index=k),
                "split": split,
            }
        )

    # ---- balões ------------------------------------------------------------------------
    callouts: list[dict] = []

    def callout(t: float, kind: str, title_: str, value: str, sub: str = "", big=False) -> None:
        callouts.append(
            {
                "t": round(t, 3),
                "until": round(t + (CALLOUT_S * (1.6 if big else 1.0)), 3),
                "kind": kind,
                "title": title_,
                "value": value,
                "sub": sub,
                "big": big,
            }
        )

    reaction = _metric(report, "reaction_s")
    if feet_off is not None and reaction is not None:
        callout(feet_off.t, "reaction", "Reação", f"{br(reaction)} s")
    bo0 = lengths[0].first(E.BREAKOUT)
    bo_m = _metric(report, "start_breakout_m")
    if bo0 is not None:
        uw = _metric(report, "start_underwater_s")
        callout(
            bo0.t,
            "breakout",
            "Saiu à tona",
            f"{br(bo_m, 1)} m" if bo_m is not None else "",
            f"{br(uw)} s submerso" if uw is not None else "",
        )
    s15 = _metric(report, "start_15m_s")
    if s15 is not None and t0 is not None:
        callout(t0 + s15, "15m", "15 m", f"{br(s15)} s", "da largada")
    for ln in lengths[:-1]:
        k = ln.index
        closes = ln.of(closing)
        data = out_lengths[k]
        if closes:
            parts = []
            if ln.of(E.STROKE):
                parts.append(f"{len(ln.of(E.STROKE))} {stroke_word.lower()}")
            if data["tempo"] is not None:
                parts.append(f"{br(data['tempo'])} s/ciclo")
            val = f"{br(data['split'])} s" if data["split"] is not None else ""
            callout(closes[-1].t, "split", f"{int((k + 1) * L)} m", val, " · ".join(parts))
        nxt = lengths[k + 1]
        tbo = nxt.first(E.BREAKOUT)
        tbo_m = _metric(report, "turn_breakout_m", turn_index=k)
        if tbo is not None:
            callout(
                tbo.t,
                "breakout",
                "Saiu à tona",
                f"{br(tbo_m, 1)} m" if tbo_m is not None else "",
                "após a virada",
            )
    if finish is not None:
        final = _metric(report, "final_time_s", length_index=len(lengths) - 1)
        m = report.get("final_time_s", length_index=len(lengths) - 1)
        sub = "tempo oficial" if m is not None and m.source == "official" else ""
        callout(
            finish.t, "finish", "Chegada!", f"{clock_text(final)} s" if final else "", sub, True
        )
    callouts.sort(key=lambda c: c["t"])

    # ---- resumo final ------------------------------------------------------------------
    rows = []
    if reaction is not None:
        rows.append(["Reação", f"{br(reaction)} s"])
    if s15 is not None:
        rows.append(["15 m", f"{br(s15)} s"])
    for d in out_lengths:
        if d["split"] is not None:
            lab = f"{int((d['index'] + 1) * L)} m"
            rows.append([lab, f"{clock_text(d['split'])} s"])
    tempos = [d["tempo"] for d in out_lengths if d["tempo"] is not None]
    if tempos:
        rows.append(["Tempo de ciclo", f"{br(sum(tempos) / len(tempos))} s"])
    sp = [d["speed"] for d in out_lengths if d["speed"] is not None]
    if sp:
        rows.append(["Velocidade", f"{br(sum(sp) / len(sp))} m/s"])
    n_strokes = sum(len(d["strokes"]) for d in out_lengths)
    if n_strokes:
        rows.append([stroke_word, str(n_strokes)])

    clock_end = (finish.t - t0) if (finish is not None and t0 is not None) else None
    return {
        "schema_version": 1,
        "width": width,
        "height": height,
        "duration_s": duration_s,
        "title": title,
        "athlete": athlete,
        "race_label": f"{race.distance} m {STROKE_LABEL[race.stroke]}",
        "pool_label": f"Piscina {int(L)} m",
        "lane": race.lane,
        "distance": race.distance,
        "pool_length": L,
        "n_lengths": race.n_lengths,
        "stroke_word": stroke_word,
        # sem braçadas nem velocidade, o painel só mostraria zeros e traços: fica escondido
        "has_swim_data": bool(n_strokes) or any(v is not None for v in speeds),
        "t0": t0,
        "t_finish": finish.t if finish is not None else None,
        "clock_end": clock_end,
        "phases": phases,
        "lengths": out_lengths,
        "callouts": callouts,
        "track": {
            "t": [round(s.t, 3) for s in track],
            "d": [round(s.race_d, 2) for s in track],
            "x": [None if s.x is None else round(s.x, 1) for s in track],
            "y": [None if s.y is None else round(s.y, 1) for s in track],
            "v": speeds,
        },
        "summary": rows,
    }


# ---- estado num instante (mesmas regras de frontend/src/overlay/state.ts) ------------------


def _interp(ts: list[float], vs: list, t: float):
    """Interpolação linear; None se o valor vizinho for None."""
    if not ts:
        return None
    i = int(np.searchsorted(ts, t))
    if i <= 0:
        return vs[0]
    if i >= len(ts):
        return vs[-1]
    a, b = vs[i - 1], vs[i]
    if a is None or b is None:
        return a if t - ts[i - 1] < ts[i] - t else b
    f = (t - ts[i - 1]) / (ts[i] - ts[i - 1])
    return a + f * (b - a)


def state_at(tl: dict, t: float) -> dict:
    t0, tf = tl["t0"], tl["t_finish"]
    if t0 is None:
        clock = None
    elif tf is not None and t >= tf:
        clock = tl["clock_end"]
    else:
        clock = max(0.0, t - t0)
    ph = next(
        (p for p in tl["phases"] if p["t0"] <= t and (p["t1"] is None or t < p["t1"])),
        None,
    )
    k = ph["length"] if ph else 0
    for ln in tl["lengths"]:
        if ln["t_end"] is not None and t >= ln["t_end"] and ln["index"] < tl["n_lengths"] - 1:
            k = max(k, ln["index"] + 1)
    ln = tl["lengths"][min(k, len(tl["lengths"]) - 1)]
    done = [s for s in ln["strokes"] if s[0] <= t]
    tempo = next((s[1] for s in reversed(done) if s[1] is not None), None)
    tr = tl["track"]
    d = _interp(tr["t"], tr["d"], t)
    v = _interp(tr["t"], tr["v"], t)
    x = _interp(tr["t"], tr["x"], t)
    y = _interp(tr["t"], tr["y"], t)
    kind = ph["kind"] if ph else None
    if kind not in ("swim", "underwater", "turn"):
        v = None
    active = [c for c in tl["callouts"] if c["t"] <= t < c["until"]]
    return {
        "clock": clock,
        "phase": kind,
        "phase_label": ph["label"] if ph else None,
        "length": ln["index"],
        "strokes": len(done),
        "tempo": tempo,
        "speed": v,
        "race_d": d,
        "head": [x, y] if x is not None and y is not None else None,
        "callouts": active[-2:],
        # resumo depois do balão de chegada, ou no fim do vídeo se ele acabar antes
        "show_summary": tf is not None
        and t >= tf
        and t >= min(tf + CALLOUT_S * 1.6, (tl["duration_s"] or 1e9) - SUMMARY_TAIL_S),
    }
