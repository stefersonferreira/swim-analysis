"""Linha do tempo da sobreposição: relógio, fases, braçadas correntes e balões."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from swimcv.contracts import EventType
from swimcv.metrics import compute_metrics
from swimcv.overlay import build_timeline, clock_text, state_at
from tests.unit.test_metrics import breast_50m, reference_free_50m


def free_timeline(**kw):
    race, evs = reference_free_50m()
    return build_timeline(race, evs, compute_metrics(race, evs), title="50 livre", **kw)


def test_clock_runs_from_start_and_freezes_at_finish():
    tl = free_timeline()
    assert state_at(tl, 0.5)["clock"] == 0.0
    assert state_at(tl, 6.0)["clock"] == pytest.approx(5.0)
    assert state_at(tl, 30.0)["clock"] == pytest.approx(21.80)
    assert clock_text(21.8) == "21,80" and clock_text(62.35) == "1:02,35"


def test_phases_in_order():
    tl = free_timeline()
    kinds = [state_at(tl, t)["phase"] for t in (0.5, 1.5, 4.0, 8.0, 11.0, 12.5, 16.0, 23.0)]
    assert kinds == [
        "ready",
        "start",
        "underwater",
        "swim",
        "turn",
        "underwater",
        "swim",
        "finish",
    ]
    json.dumps(tl)  # serializável como está


def test_running_strokes_and_tempo_per_length():
    tl = free_timeline()
    s = state_at(tl, 6.10 + 0.48 * 4 + 0.01)  # 5ª braçada da piscina 1
    assert s["length"] == 0 and s["strokes"] == 5
    assert s["tempo"] == pytest.approx(0.96)
    s = state_at(tl, 14.5)  # piscina 2: conta de novo
    assert s["length"] == 1 and 1 <= s["strokes"] <= 2


def test_callouts_and_summary():
    tl = free_timeline()
    kinds = [c["kind"] for c in tl["callouts"]]
    assert kinds == ["reaction", "breakout", "15m", "split", "breakout", "finish"]
    split = next(c for c in tl["callouts"] if c["kind"] == "split")
    assert split["title"] == "25 m" and split["value"] == "10,58 s"
    assert "12 braçadas" in split["sub"]
    fin = tl["callouts"][-1]
    assert fin["value"] == "21,80 s" and fin["sub"] == "tempo oficial"
    assert [c["kind"] for c in state_at(tl, 1.7)["callouts"]] == ["reaction"]
    assert state_at(tl, 30)["show_summary"] and not state_at(tl, 23)["show_summary"]
    assert ["Reação", "0,67 s"] in tl["summary"] and ["50 m", "21,80 s"] in tl["summary"]


def test_race_distance_without_trajectory_from_events():
    tl = free_timeline()
    assert state_at(tl, 0.5)["race_d"] == 0
    assert state_at(tl, 5.96)["race_d"] == pytest.approx(9.9)
    assert state_at(tl, 11.58)["race_d"] == pytest.approx(25.0)
    assert state_at(tl, 23.0)["race_d"] == pytest.approx(50.0)
    assert state_at(tl, 8)["head"] is None


def test_trajectory_gives_head_and_speed():
    race, evs = reference_free_50m()
    ts = [i / 30 for i in range(30 * 25)]
    # cabeça a 2 m/s na ida, volta depois de 11,58 s
    head = [
        min(25.0, max(0.0, 2.0 * (t - 1.67))) if t < 11.58 else max(0.0, 25 - 2.0 * (t - 11.58))
        for t in ts
    ]
    traj = {
        "t": ts,
        "head_x": head,
        "head_img_x": [100 + 10 * h for h in head],
        "head_img_y": [300.0] * len(ts),
    }
    tl = build_timeline(race, evs, compute_metrics(race, evs), trajectory=traj)
    s = state_at(tl, 8.0)
    assert s["race_d"] == pytest.approx(2.0 * (8.0 - 1.67), abs=0.15)
    assert s["speed"] == pytest.approx(2.0, abs=0.05)
    assert s["head"][0] == pytest.approx(100 + 10 * s["race_d"], abs=2)
    s = state_at(tl, 14.0)
    assert s["race_d"] == pytest.approx(25 + 2.0 * (14.0 - 11.58), abs=0.15)
    assert state_at(tl, 0.5)["speed"] is None  # parado no bloco: não mostra


def test_breaststroke_uses_cycles_and_hands_touch():
    race, evs = breast_50m()
    tl = build_timeline(race, evs, compute_metrics(race, evs))
    assert tl["stroke_word"] == "Ciclos"
    assert state_at(tl, 18.6)["phase"] == "turn"
    s = state_at(tl, 6.40 + 1.20 * 3 + 0.01)
    assert s["strokes"] == 4 and s["tempo"] == pytest.approx(1.20)
    split = next(c for c in tl["callouts"] if c["kind"] == "split")
    assert split["t"] == pytest.approx(18.30) and "9 ciclos" in split["sub"]


def test_sparse_events_do_not_break():
    race, evs = reference_free_50m()
    evs = [e for e in evs if e.type == EventType.STROKE]
    tl = build_timeline(race, evs, compute_metrics(race, evs))
    s = state_at(tl, 8.0)
    assert s["clock"] is None and s["strokes"] >= 1
    assert tl["callouts"] == []


@pytest.mark.skipif(not shutil.which("node"), reason="node não instalado")
@pytest.mark.parametrize("which", ["free", "free_traj", "breast"])
def test_browser_state_matches_python(tmp_path, which):
    """state.ts (navegador) e state_at (MP4) dão o mesmo resultado."""
    if which == "breast":
        race, evs = breast_50m()
        tl = build_timeline(race, evs, compute_metrics(race, evs))
    else:
        race, evs = reference_free_50m()
        traj = None
        if which == "free_traj":
            ts = [i / 30 for i in range(30 * 25)]
            head = [min(25.0, max(0.0, 2.0 * (t - 1.67))) for t in ts]
            traj = {"t": ts, "head_x": head, "head_img_x": head, "head_img_y": [5.0] * len(ts)}
        tl = build_timeline(race, evs, compute_metrics(race, evs), trajectory=traj)
    times = [i * 0.137 for i in range(300)]
    f = tmp_path / "in.json"
    f.write_text(json.dumps({"timeline": tl, "times": times}))
    out = subprocess.run(
        ["node", "--experimental-strip-types", "--no-warnings", "tools/overlay_state.mjs", str(f)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    js = json.loads(out.stdout)
    keys = {"phase_label": "phaseLabel", "race_d": "raceD", "show_summary": "showSummary"}
    for t, b in zip(times, js, strict=True):
        a = state_at(tl, t)
        for k, v in a.items():
            w = b[keys.get(k, k)]
            if isinstance(v, float) or isinstance(w, float):
                assert v == pytest.approx(w, abs=1e-6), (t, k, v, w)
            elif k == "head":
                assert (v is None) == (w is None) and (v is None or v == pytest.approx(w)), (t, k)
            else:
                assert v == w, (t, k, v, w)


def test_summary_at_end_of_short_video():
    race, evs = reference_free_50m()
    tl = build_timeline(race, evs, compute_metrics(race, evs), duration_s=23.5)
    assert not state_at(tl, 22.9)["show_summary"]
    assert state_at(tl, 23.3)["show_summary"]


def test_only_start_marked_does_not_fake_a_phase_or_panel():
    """Vídeo real de treino só com o apito marcado: 'Saída' some e o painel não aparece."""
    race, evs = reference_free_50m()
    start = [e for e in evs if e.type == EventType.START_SIGNAL]
    tl = build_timeline(race, start, compute_metrics(race, start))
    assert tl["has_swim_data"] is False
    t0 = start[0].t
    assert state_at(tl, t0 + 0.5)["phase"] == "start"
    assert state_at(tl, t0 + 5.0)["phase"] is None
    assert state_at(tl, t0 + 5.0)["clock"] is not None  # o relógio continua
    full = free_timeline()
    assert full["has_swim_data"] is True
