"""Calibração por cliques: homografia imagem -> plano da água (metros)."""

from __future__ import annotations

import cv2
import numpy as np

from swimcv.contracts import Anchor, AnchorResult, Calibration

MIN_POINTS = 4
MAX_MEAN_ERROR_M = 0.15
MAX_POINT_ERROR_M = 0.30
RANSAC_THRESHOLD_M = 0.5


def project(h: list[list[float]] | np.ndarray, image_pts) -> np.ndarray:
    """Projeta pontos da imagem (N x 2) para a piscina (N x 2) em metros."""
    pts = np.asarray(image_pts, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, np.asarray(h, dtype=np.float64)).reshape(-1, 2)


def inverse_project(h: list[list[float]] | np.ndarray, pool_pts) -> np.ndarray:
    """Projeta pontos da piscina (metros) para a imagem (pixels)."""
    inv = np.linalg.inv(np.asarray(h, dtype=np.float64))
    pts = np.asarray(pool_pts, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, inv).reshape(-1, 2)


def _degenerate(pool: np.ndarray) -> bool:
    """Pontos quase colineares na piscina não definem uma homografia."""
    centered = pool - pool.mean(axis=0)
    s = np.linalg.svd(centered, compute_uv=False)
    return s[-1] < 0.5  # espalhamento menor que ~0,5 m na direção mais estreita


def solve_anchor(anchor: Anchor) -> AnchorResult:
    n = len(anchor.points)
    if n < MIN_POINTS:
        return AnchorResult(
            frame=anchor.frame, message=f"precisa de {MIN_POINTS} pontos ({n} marcados)"
        )
    img = np.array([p.image_xy for p in anchor.points], dtype=np.float64)
    pool = np.array([p.pool_xy for p in anchor.points], dtype=np.float64)
    if _degenerate(pool):
        return AnchorResult(
            frame=anchor.frame,
            message="pontos quase em linha: use pontos em pelo menos duas cordas diferentes",
        )
    method = cv2.RANSAC if n > MIN_POINTS else 0
    h, mask = cv2.findHomography(img, pool, method, RANSAC_THRESHOLD_M)
    if h is None:
        return AnchorResult(frame=anchor.frame, message="não foi possível calcular a homografia")
    inliers = mask.ravel().astype(bool) if mask is not None else np.ones(n, bool)
    errs = np.linalg.norm(project(h, img) - pool, axis=1)
    used = errs[inliers]
    mean_e, max_e = float(used.mean()), float(used.max())
    accepted = mean_e <= MAX_MEAN_ERROR_M and max_e <= MAX_POINT_ERROR_M and inliers.sum() >= 4
    msg = None
    if not accepted:
        msg = (
            f"erro médio {mean_e:.2f} m (limite {MAX_MEAN_ERROR_M}) e máximo {max_e:.2f} m "
            f"(limite {MAX_POINT_ERROR_M}): confira ou acrescente pontos"
        )
    if (~inliers).any():
        bad = ", ".join(str(i + 1) for i in np.flatnonzero(~inliers))
        msg = (msg + "; " if msg else "") + f"pontos descartados como errados: {bad}"
    return AnchorResult(
        frame=anchor.frame,
        homography=h.tolist(),
        mean_error_m=mean_e,
        max_error_m=max_e,
        point_errors_m=[float(e) for e in errs],
        inliers=[bool(x) for x in inliers],
        accepted=bool(accepted),
        message=msg,
    )


def solve(calibration: Calibration) -> Calibration:
    results = [solve_anchor(a) for a in sorted(calibration.anchors, key=lambda a: a.frame)]
    return calibration.model_copy(update={"results": results})


def grid_lines(calibration: Calibration, result: AnchorResult, step_m: float = 5.0):
    """Linhas da grade da piscina em pixels, para desenhar sobre o quadro."""
    pool = calibration.pool
    lines = []
    xs = np.arange(0.0, pool.length_m + 1e-6, step_m).tolist()
    if pool.length_m not in xs:
        xs.append(pool.length_m)
    for x in xs:
        seg = inverse_project(result.homography, [(x, 0.0), (x, pool.width_m)])
        lines.append({"kind": "x", "value": x, "points": seg.tolist()})
    for r in range(pool.lanes + 1):
        y = pool.rope_y(r)
        seg = inverse_project(result.homography, [(0.0, y), (pool.length_m, y)])
        lines.append({"kind": "rope", "value": r, "points": seg.tolist()})
    return lines
