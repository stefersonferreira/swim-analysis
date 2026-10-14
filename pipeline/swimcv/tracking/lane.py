"""Rastreamento do nadador na própria raia (módulos 4 a 6, versão clássica sem modelo).

1. Para cada quadro, a faixa da raia é "desentortada" para uma grade vista de cima em metros
   (x ao longo da piscina, y através da raia), usando a homografia do quadro. Só o miolo da
   raia entra (as cordas ficam de fora), então nadadores das raias vizinhas não contam.
2. Em cada coluna (posição x) mede-se o quanto a água foge do normal: cor diferente da água
   daquele quadro e espuma branca. O que é fixo no fundo (faixa preta, cruzes) é removido
   subtraindo a mediana no tempo de cada coluna.
3. Um nadador ocupa ~2,5 m (corpo + braços + pernada): o perfil é suavizado com essa janela e
   o caminho mais provável no tempo é escolhido por programação dinâmica (Viterbi) com
   velocidade máxima de 3,5 m/s, o que ignora respingos soltos.
4. A cabeça fica à frente do centro do corpo, no sentido do nado (HEAD_OFFSET_M).

Saída: trajetória quadro a quadro (posição da cabeça em metros, confiança) e o sinal de espuma
na frente do nadador, usado para braçadas e breakout.

Um detector com IA (RT-DETR) pode substituir o passo 2 depois, com a mesma saída.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import av
import cv2
import numpy as np
import pandas as pd

STEP_M = 0.1
HALF_LANE_INNER_M = 0.85  # miolo da raia (a corda fica a 1,25 m do centro)
BODY_M = 2.5
MAX_SPEED_MPS = 3.5
HEAD_OFFSET_M = 0.8
WORK_W = 960


@dataclass
class LaneSignals:
    xs: np.ndarray  # (ncols,) posição de cada coluna, m
    anomaly: np.ndarray  # (n, ncols) água fora do normal (0..)
    white: np.ndarray  # (n, ncols) fração de espuma branca
    valid: np.ndarray  # (n, ncols) coluna visível no quadro

    def save(self, path: Path) -> None:
        np.savez_compressed(
            path,
            xs=self.xs,
            anomaly=self.anomaly.astype(np.float16),
            white=self.white.astype(np.float16),
            valid=self.valid,
        )

    @classmethod
    def load(cls, path: Path) -> LaneSignals:
        d = np.load(path)
        return cls(
            d["xs"], d["anomaly"].astype(np.float32), d["white"].astype(np.float32), d["valid"]
        )


def lane_grid(pool_length: float, lane_center_y: float) -> tuple[np.ndarray, np.ndarray]:
    xs = np.arange(-1.0, pool_length + 1.0 + 1e-6, STEP_M)
    ys = np.arange(-HALF_LANE_INNER_M, HALF_LANE_INNER_M + 1e-6, STEP_M) + lane_center_y
    return xs, ys


def extract_signals(
    proxy: Path, homographies: np.ndarray, pool_length: float, lane_center_y: float
) -> LaneSignals:
    xs, ys = lane_grid(pool_length, lane_center_y)
    gx, gy = np.meshgrid(xs, ys)
    pool_pts = np.stack([gx.ravel(), gy.ravel()], axis=1).astype(np.float64).reshape(-1, 1, 2)
    n = len(homographies)
    anomaly = np.zeros((n, len(xs)), np.float32)
    white = np.zeros((n, len(xs)), np.float32)
    valid = np.zeros((n, len(xs)), bool)
    scale = None
    with av.open(str(proxy)) as c:
        s = c.streams.video[0]
        s.thread_type = "AUTO"
        for t, f in enumerate(c.decode(s)):
            if t >= n:
                break
            img = f.to_ndarray(format="bgr24")
            if scale is None:
                scale = min(1.0, WORK_W / img.shape[1])
            if scale < 1.0:
                img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            inv = np.linalg.inv(homographies[t])
            ip = cv2.perspectiveTransform(pool_pts, inv).reshape(gy.shape + (2,)) * scale
            mx, my = ip[..., 0].astype(np.float32), ip[..., 1].astype(np.float32)
            inside = (mx >= 0) & (mx < img.shape[1] - 1) & (my >= 0) & (my < img.shape[0] - 1)
            strip = cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            lab = cv2.cvtColor(strip, cv2.COLOR_BGR2LAB).astype(np.float32)
            ok = inside
            if ok.sum() < 20:
                continue
            ref = np.median(lab[ok], axis=0)
            dev = np.linalg.norm(lab - ref, axis=2)
            light = lab[..., 0]
            chroma = np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
            foam = (light > ref[0] + 25) & (chroma < 25)
            cnt = ok.sum(axis=0)
            vis = cnt >= max(3, 0.5 * ok.shape[0])
            anomaly[t] = np.where(vis, (dev * ok).sum(axis=0) / np.maximum(cnt, 1), 0)
            white[t] = np.where(vis, (foam & ok).sum(axis=0) / np.maximum(cnt, 1), 0)
            valid[t] = vis
    return LaneSignals(xs=xs, anomaly=anomaly, white=white, valid=valid)


def _remove_static(sig: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Tira o que é fixo em cada posição (fundo da piscina) e normaliza por quadro."""
    masked = np.where(valid, sig, np.nan)
    with np.errstate(all="ignore"):
        col_med = np.nanmedian(masked, axis=0)
    col_med = np.nan_to_num(col_med)
    out = np.where(valid, sig - col_med[None, :], 0.0)
    out = np.clip(out, 0, None)
    # escala robusta por quadro
    with np.errstate(all="ignore"):
        q = np.nanpercentile(np.where(valid, out, np.nan), 90, axis=1)
    q = np.nan_to_num(q, nan=1.0)
    return out / (q[:, None] + 1.0)


@dataclass
class Trajectory:
    t: np.ndarray  # (n,) PTS
    body_x: np.ndarray  # centro do corpo, m
    head_x: np.ndarray  # cabeça, m
    direction: np.ndarray  # +1 indo para a parede oposta, -1 voltando
    confidence: np.ndarray  # 0..1
    front_white: np.ndarray  # espuma à frente do nadador (braçadas, breakout)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "frame": np.arange(len(self.t)),
                "t": self.t,
                "body_x": self.body_x,
                "head_x": self.head_x,
                "direction": self.direction,
                "confidence": self.confidence,
                "front_white": self.front_white,
            }
        )

    @classmethod
    def from_frame(cls, df: pd.DataFrame) -> Trajectory:
        return cls(
            df["t"].to_numpy(),
            df["body_x"].to_numpy(),
            df["head_x"].to_numpy(),
            df["direction"].to_numpy(),
            df["confidence"].to_numpy(),
            df["front_white"].to_numpy(),
        )


def track(sig: LaneSignals, pts: np.ndarray, pool_length: float) -> Trajectory:
    n, m = sig.anomaly.shape
    a = _remove_static(sig.anomaly, sig.valid)
    w = _remove_static(sig.white, sig.valid)
    score = a + 1.5 * w
    k = max(1, int(round(BODY_M / STEP_M)))
    kernel = np.ones(k) / k
    blob = np.array([np.convolve(row, kernel, mode="same") for row in score])

    # Viterbi: estado = coluna; passo máximo por quadro conforme o tempo real (taxa variável)
    dt = np.diff(pts, prepend=pts[0] - (pts[1] - pts[0] if n > 1 else 1 / 30))
    log_e = blob  # emissão já normalizada
    best = log_e[0].copy()
    back = np.zeros((n, m), np.int32)
    idx = np.arange(m)
    for t in range(1, n):
        r = max(1, int(np.ceil(MAX_SPEED_MPS * max(dt[t], 1e-3) / STEP_M)))
        cand = np.full((2 * r + 1, m), -np.inf)
        for j, d in enumerate(range(-r, r + 1)):
            src = idx - d
            okk = (src >= 0) & (src < m)
            cand[j, okk] = best[src[okk]] - 0.02 * abs(d)
        arg = cand.argmax(axis=0)
        back[t] = idx - (arg - r)
        best = cand[arg, idx] + log_e[t]
    path = np.zeros(n, np.int32)
    path[-1] = int(best.argmax())
    for t in range(n - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    body = sig.xs[path].astype(float)
    # suaviza (0,2 s) e mede confiança pelo contraste do pico
    win = 5
    body_s = np.convolve(
        np.pad(body, win, mode="edge"), np.ones(2 * win + 1) / (2 * win + 1), mode="same"
    )[win:-win]
    peak = blob[np.arange(n), path]
    others = np.median(blob, axis=1)
    conf = np.clip((peak - others) / (peak + 1e-6), 0, 1)
    vel = np.gradient(body_s, pts)
    vel_s = np.convolve(np.pad(vel, 8, mode="edge"), np.ones(17) / 17, mode="same")[8:-8]
    direction = np.where(vel_s >= 0, 1, -1)
    head = np.clip(body_s + direction * HEAD_OFFSET_M, 0, pool_length)
    # espuma à frente: entre a cabeça e 1 m adiante dela
    front = np.zeros(n)
    for t in range(n):
        lo, hi = sorted((head[t] - 0.3 * direction[t], head[t] + 0.9 * direction[t]))
        cols = (sig.xs >= lo) & (sig.xs <= hi)
        if cols.any():
            front[t] = float(sig.white[t, cols].mean())
    return Trajectory(
        t=pts, body_x=body_s, head_x=head, direction=direction, confidence=conf, front_white=front
    )
