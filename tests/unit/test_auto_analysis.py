"""Análise automática ponta a ponta em provas sintéticas com verdade conhecida.

Metas (próximas das da spec para o automático sem revisão): braçadas ±1 por piscina, 15 m a
±0,15 s, breakout a ±0,75 m, chegada a ±0,15 s, largada a ±0,02 s.
"""

import shutil

import numpy as np
import pytest

from swimcv.analyze import run
from swimcv.calibration import solve
from swimcv.camera import CameraMotion
from swimcv.contracts import (
    Anchor,
    Calibration,
    ClickPoint,
    EventType,
    PoolProfile,
    RaceInfo,
    Stroke,
)
from swimcv.ingest import ingest_video
from swimcv.metrics import compute_metrics, resolve_positions
from swimcv.storage import VideoPaths
from tests.synthetic import FPS, anchor_points

E = EventType
pytestmark = [pytest.mark.video, pytest.mark.slow]


@pytest.fixture(scope="module", params=["static", "moving"])
def analyzed(request, synthetic_videos, tmp_path_factory):
    src, moving, truth = synthetic_videos[request.param]
    paths = VideoPaths.for_video(tmp_path_factory.mktemp("data"), request.param).ensure()
    shutil.copy(src, paths.original(".mp4"))
    ingest_video(paths)
    a = 150
    pts = anchor_points(a / FPS, moving, truth)
    cal = solve(
        Calibration(
            pool=PoolProfile(length_m=25, lanes=8, lane_width_m=2.5),
            anchors=[
                Anchor(
                    frame=a,
                    points=[
                        ClickPoint(image_xy=tuple(p["image_xy"]), pool_xy=tuple(p["pool_xy"]))
                        for p in pts
                    ],
                )
            ],
        )
    )
    race = RaceInfo(stroke=Stroke.FREESTYLE, distance=50, pool_length=25, lane=truth.lane)
    events, notes = run(paths, race, cal)
    return request.param, paths, truth, race, cal, events, notes


def _times(events, kind):
    return [e.t for e in events if e.type == kind]


def test_camera_motion_detected(analyzed):
    name, paths, *_ = analyzed
    motion = CameraMotion.load(paths.root / "analysis" / "camera_motion.npz")
    assert motion.static is (name == "static")


def test_start_entry_and_walls(analyzed):
    _, _, truth, _, _, events, _ = analyzed
    assert _times(events, E.START_SIGNAL)[0] == pytest.approx(truth.start_t, abs=0.02)
    assert _times(events, E.ENTRY)[0] == pytest.approx(truth.entry_t, abs=0.1)
    (wall,) = _times(events, E.WALL_FEET)
    assert truth.wall_t - 0.1 <= wall <= truth.pushoff_t + 0.1
    assert _times(events, E.FINISH_TOUCH)[0] == pytest.approx(truth.finish_t, abs=0.15)


def test_strokes_per_length(analyzed):
    _, _, truth, _, _, events, _ = analyzed
    st = _times(events, E.STROKE)
    for lo, hi in ((0, truth.wall_t), (truth.wall_t, 99)):
        auto = len([t for t in st if lo <= t < hi])
        real = len([t for t in truth.strokes if lo <= t < hi])
        assert abs(auto - real) <= 1, (lo, auto, real)


def test_metrics_close_to_truth(analyzed):
    _, _, truth, race, cal, events, _ = analyzed
    H = np.load(analyzed[1].root / "analysis" / "homographies.npy")
    r = compute_metrics(race, resolve_positions(events, cal, H))
    t15 = next(t / 1000 for t in range(0, 30000) if truth.head_x(t / 1000) >= 15)
    assert r.value("start_15m_s") == pytest.approx(t15 - truth.start_t, abs=0.15)
    assert r.value("start_breakout_m") == pytest.approx(truth.breakout_x, abs=0.75)
    assert r.value("turn_breakout_m", turn_index=0) == pytest.approx(truth.breakout2_d, abs=0.75)
    assert r.value("tempo_s_per_cycle", length_index=1) == pytest.approx(
        2 * truth.arm_period, abs=0.05
    )
    assert r.value("swim_speed_mps", length_index=0) == pytest.approx(truth.v1, abs=0.1)
    assert r.value("final_time_s", length_index=1) == pytest.approx(
        truth.finish_t - truth.start_t, abs=0.15
    )


def test_needs_lane(analyzed):
    from swimcv.analyze import AnalysisError

    _, paths, _, race, cal, _, _ = analyzed
    with pytest.raises(AnalysisError, match="raia"):
        run(paths, race.model_copy(update={"lane": None}), cal)
