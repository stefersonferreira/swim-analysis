"""Movimento da câmera (módulo 2) e homografia por quadro (propagação da calibração, entrega 5).

Pontos de textura fora da água (arquibancada, paredes, bandeiras) são seguidos de um quadro-chave
até o quadro atual com fluxo óptico (Lucas-Kanade) e uma homografia é ajustada com RANSAC. A água
é excluída porque as ondas se movem sozinhas. Comparar sempre com o quadro-chave (e não com o
quadro anterior) evita acumular erro: um novo quadro-chave só é criado quando a vista mudou muito.

Resultado: C[t] leva coordenadas da imagem do quadro t para as do quadro 0. Com a homografia de uma
âncora A (imagem da âncora -> piscina), a do quadro t é  A · C[a]⁻¹ · C[t].
Câmera parada (trípé) é detectada e vira identidade em todos os quadros, sem ruído.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import av
import cv2
import numpy as np

WORK_W = 640
MAX_CORNERS = 500
MIN_INLIERS = 25
STATIC_PX = 0.35  # movimento mediano (px do proxy) abaixo disso = câmera parada


@dataclass
class CameraMotion:
    to_ref: np.ndarray  # (n, 3, 3): imagem do quadro t -> imagem do quadro 0
    quality: np.ndarray  # (n,) fração de pontos inliers (0..1); 0 = estimado por interpolação
    static: bool

    def save(self, path: Path) -> None:
        np.savez_compressed(path, to_ref=self.to_ref, quality=self.quality, static=self.static)

    @classmethod
    def load(cls, path: Path) -> CameraMotion:
        d = np.load(path)
        return cls(to_ref=d["to_ref"], quality=d["quality"], static=bool(d["static"]))


def water_mask(bgr: np.ndarray) -> np.ndarray:
    """255 onde parece água de piscina (azul/ciano saturado)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    water = (h >= 80) & (h <= 115) & (s >= 50) & (v >= 60)
    m = water.astype(np.uint8) * 255
    return cv2.dilate(m, np.ones((9, 9), np.uint8))


def _frames(proxy: Path):
    with av.open(str(proxy)) as c:
        s = c.streams.video[0]
        s.thread_type = "AUTO"
        for f in c.decode(s):
            yield f.to_ndarray(format="bgr24")


def estimate(proxy: Path, n_frames: int | None = None) -> CameraMotion:
    to_ref: list[np.ndarray] = []
    quality: list[float] = []
    motions: list[float] = []
    key_gray = key_pts = None
    key_C = np.eye(3)
    scale = None
    for frame in _frames(proxy):
        if scale is None:
            scale = WORK_W / frame.shape[1]
            Sm = np.diag([scale, scale, 1.0])
            Sinv = np.linalg.inv(Sm)
        small = cv2.resize(
            frame, (WORK_W, int(round(frame.shape[0] * scale))), interpolation=cv2.INTER_AREA
        )
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        mask = cv2.bitwise_not(water_mask(small))
        if key_gray is None:
            key_gray, key_C = gray, np.eye(3)
            key_pts = cv2.goodFeaturesToTrack(gray, MAX_CORNERS, 0.01, 7, mask=mask)
            to_ref.append(np.eye(3))
            quality.append(1.0)
            prev = (gray, mask)
            continue
        H_small, q, med = _match(key_gray, key_pts, gray)
        if H_small is None:
            # perdeu o quadro-chave: tenta a partir do quadro anterior
            prev_gray = prev[0]
            prev_pts = cv2.goodFeaturesToTrack(prev_gray, MAX_CORNERS, 0.01, 7, mask=prev[1])
            H_prev, q, med = _match(prev_gray, prev_pts, gray)
            if H_prev is None:
                C = to_ref[-1].copy()  # mantém o último conhecido
                q = 0.0
            else:
                C = to_ref[-1] @ np.linalg.inv(Sinv @ H_prev @ Sm)
            key_gray, key_C = gray, C
            key_pts = cv2.goodFeaturesToTrack(gray, MAX_CORNERS, 0.01, 7, mask=mask)
        else:
            # H_small: quadro-chave -> atual (coordenadas reduzidas)
            C = key_C @ np.linalg.inv(Sinv @ H_small @ Sm)
            if q < 0.5 or med > 80:
                key_gray, key_C = gray, C
                key_pts = cv2.goodFeaturesToTrack(gray, MAX_CORNERS, 0.01, 7, mask=mask)
        motions.append(med / scale if med is not None else 0.0)
        to_ref.append(C)
        quality.append(float(q))
        prev = (gray, mask)
        if n_frames and len(to_ref) >= n_frames:
            break
    arr = np.array(to_ref)
    static = bool(motions) and float(np.percentile(np.abs(motions), 95)) < STATIC_PX
    if static:
        arr = np.repeat(np.eye(3)[None], len(arr), axis=0)
    return CameraMotion(to_ref=arr, quality=np.array(quality), static=static)


def _match(g0: np.ndarray, p0, g1: np.ndarray):
    if p0 is None or len(p0) < MIN_INLIERS:
        return None, 0.0, None
    p1, st, _ = cv2.calcOpticalFlowPyrLK(
        g0,
        g1,
        p0,
        None,
        winSize=(21, 21),
        maxLevel=4,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
    )
    ok = st.ravel() == 1
    if ok.sum() < MIN_INLIERS:
        return None, 0.0, None
    a, b = p0[ok].reshape(-1, 2), p1[ok].reshape(-1, 2)
    H, inl = cv2.findHomography(a, b, cv2.RANSAC, 1.5)
    if H is None or inl is None or inl.sum() < MIN_INLIERS:
        return None, 0.0, None
    inl = inl.ravel().astype(bool)
    med = float(np.median(np.linalg.norm(b[inl] - a[inl], axis=1)))
    return H, float(inl.sum()) / len(p0), med


def frame_homographies(
    motion: CameraMotion | None, anchors: list[tuple[int, np.ndarray]], n_frames: int
) -> np.ndarray:
    """Homografia imagem -> piscina para cada quadro, a partir das âncoras aceitas.

    Cada quadro usa a âncora mais próxima no tempo (menos deriva acumulada).
    """
    if not anchors:
        raise ValueError("nenhuma âncora de calibração aceita")
    frames = np.array([f for f, _ in anchors])
    out = np.empty((n_frames, 3, 3))
    for t in range(n_frames):
        i = int(np.argmin(np.abs(frames - t)))
        fa, A = anchors[i]
        if motion is None or motion.static:
            out[t] = A
        else:
            fa = min(fa, len(motion.to_ref) - 1)
            tt = min(t, len(motion.to_ref) - 1)
            out[t] = A @ np.linalg.inv(motion.to_ref[fa]) @ motion.to_ref[tt]
        out[t] /= out[t][2, 2]
    return out
