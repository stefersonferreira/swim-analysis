import numpy as np
import pytest

from swimcv.calibration import grid_lines, inverse_project, project, solve
from swimcv.contracts import Anchor, Calibration, ClickPoint, Event, EventType, PoolProfile
from swimcv.metrics import resolve_positions

# Câmera sintética: homografia piscina (m) -> imagem (px) de uma vista oblíqua da borda.
H_POOL_TO_IMG = np.array([[38.0, -9.0, 120.0], [2.0, 14.0, 300.0], [0.0, -0.012, 1.0]])


def to_img(pool_pts):
    pts = np.asarray(pool_pts, float).reshape(-1, 1, 2)
    import cv2

    return cv2.perspectiveTransform(pts, H_POOL_TO_IMG).reshape(-1, 2)


def make_anchor(pool_pts, noise_px=0.0, seed=0):
    rng = np.random.default_rng(seed)
    img = to_img(pool_pts) + rng.normal(0, noise_px, (len(pool_pts), 2))
    return Anchor(
        frame=10,
        points=[
            ClickPoint(image_xy=tuple(i), pool_xy=tuple(p))
            for i, p in zip(img, pool_pts, strict=True)
        ],
    )


POOL = PoolProfile(length_m=25, lanes=6, lane_width_m=2.5)
PTS = [(0, 0), (0, 7.5), (15, 0), (15, 7.5), (25, 0), (25, 7.5), (10, 15), (5, 2.5)]


def test_exact_points_give_zero_error():
    cal = solve(Calibration(pool=POOL, anchors=[make_anchor(PTS)]))
    r = cal.results[0]
    assert r.accepted and r.mean_error_m < 1e-6
    back = inverse_project(r.homography, [(12.5, 5.0)])
    assert np.allclose(project(r.homography, back), [(12.5, 5.0)], atol=1e-6)


def test_small_click_noise_is_accepted():
    cal = solve(Calibration(pool=POOL, anchors=[make_anchor(PTS, noise_px=0.7)]))
    assert cal.results[0].accepted


def test_wrong_click_is_flagged_as_outlier():
    anchor = make_anchor(PTS)
    p = anchor.points[3]
    anchor.points[3] = ClickPoint(image_xy=(p.image_xy[0] + 80, p.image_xy[1]), pool_xy=p.pool_xy)
    r = solve(Calibration(pool=POOL, anchors=[anchor])).results[0]
    assert r.inliers[3] is False
    assert "descartados" in (r.message or "")


def test_too_few_or_collinear_points_rejected():
    r = solve(Calibration(pool=POOL, anchors=[make_anchor(PTS[:3])])).results[0]
    assert not r.accepted and r.homography is None
    line = [(0, 0), (5, 0), (10, 0), (15, 0), (20, 0)]
    r = solve(Calibration(pool=POOL, anchors=[make_anchor(line)])).results[0]
    assert not r.accepted and "linha" in r.message


def test_resolve_positions_uses_calibration():
    cal = solve(Calibration(pool=POOL, anchors=[make_anchor(PTS)]))
    head = tuple(to_img([(12.0, 3.75)])[0])
    ev = Event(type=EventType.BREAKOUT, frame=50, t=1.0, image_xy=head)
    (out,) = resolve_positions([ev], cal)
    assert out.x_m == pytest.approx(12.0, abs=1e-6)
    assert ev.x_m is None  # original intacto


def test_grid_lines_cover_marks_and_ropes():
    cal = solve(Calibration(pool=POOL, anchors=[make_anchor(PTS)]))
    lines = grid_lines(cal, cal.results[0])
    assert len([ln for ln in lines if ln["kind"] == "rope"]) == POOL.lanes + 1
    assert {ln["value"] for ln in lines if ln["kind"] == "x"} == {0, 5, 10, 15, 20, 25}
