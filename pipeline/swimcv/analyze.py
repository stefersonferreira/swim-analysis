"""Análise automática completa de um vídeo já ingerido e calibrado.

Ordem: movimento da câmera -> homografia por quadro -> sinais da raia -> trajetória ->
eventos automáticos. Cada etapa grava seu arquivo na pasta do vídeo (analysis/), para que a
tela possa mostrar a trajetória e a grade em qualquer quadro.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from swimcv.camera import CameraMotion, estimate, frame_homographies
from swimcv.contracts import Calibration, Event, RaceInfo
from swimcv.events.auto import generate
from swimcv.events.start_signal import confidence, detect_start
from swimcv.ingest import read_frame_table
from swimcv.storage import VideoPaths
from swimcv.tracking.lane import Trajectory, extract_signals, track


class AnalysisError(Exception):
    """Falta algo para analisar (mensagem para o usuário)."""


@dataclass
class AnalysisFiles:
    root: Path

    @classmethod
    def of(cls, paths: VideoPaths) -> AnalysisFiles:
        d = paths.root / "analysis"
        d.mkdir(parents=True, exist_ok=True)
        return cls(d)

    @property
    def motion(self) -> Path:
        return self.root / "camera_motion.npz"

    @property
    def homographies(self) -> Path:
        return self.root / "homographies.npy"

    @property
    def signals(self) -> Path:
        return self.root / "lane_signals.npz"

    @property
    def trajectory(self) -> Path:
        return self.root / "trajectory.parquet"

    @property
    def start(self) -> Path:
        return self.root / "start_candidates.json"


def detect_start_signal(paths: VideoPaths) -> tuple[float | None, float, list[dict]]:
    """Roda só o áudio (não precisa de calibração). Grava os candidatos."""
    cands = detect_start(paths.audio)
    out = [
        {"t": c.t, "score": c.score, "freq_hz": c.freq_hz, "duration_s": c.duration_s}
        for c in cands
    ]
    AnalysisFiles.of(paths).start.write_text(json.dumps(out))
    if not cands:
        return None, 0.0, out
    return cands[0].t, confidence(cands), out


def load_homographies(paths: VideoPaths) -> np.ndarray | None:
    f = AnalysisFiles.of(paths).homographies
    return np.load(f) if f.exists() else None


def compute_homographies(paths: VideoPaths, cal: Calibration, n_frames: int) -> np.ndarray:
    anchors = [
        (r.frame, np.array(r.homography))
        for r in cal.results
        if r.accepted and r.homography is not None
    ]
    if not anchors:
        raise AnalysisError("Calibre a piscina antes (aba Calibração): nenhuma âncora aceita.")
    files = AnalysisFiles.of(paths)
    if files.motion.exists():
        motion = CameraMotion.load(files.motion)
    else:
        motion = estimate(paths.proxy)
        motion.save(files.motion)
    H = frame_homographies(motion, anchors, n_frames)
    np.save(files.homographies, H)
    return H


def run(paths: VideoPaths, race: RaceInfo, cal: Calibration) -> tuple[list[Event], list[str]]:
    if not race.lane:
        raise AnalysisError("Informe a raia do nadador nos dados da prova.")
    if not 1 <= race.lane <= cal.pool.lanes:
        raise AnalysisError(f"Raia {race.lane} não existe numa piscina de {cal.pool.lanes} raias.")
    if abs(cal.pool.length_m - race.pool_length_m) > 0.01:
        raise AnalysisError("O comprimento da piscina na calibração difere do da prova.")
    files = AnalysisFiles.of(paths)
    pts = read_frame_table(paths.frames)["pts"].to_numpy()
    H = compute_homographies(paths, cal, len(pts))
    lane_y = cal.pool.lane_center_y(race.lane)
    sig = extract_signals(paths.proxy, H, race.pool_length_m, lane_y)
    sig.save(files.signals)
    traj = track(sig, pts, race.pool_length_m)
    df = traj.to_frame()
    # posição da cabeça na imagem, para desenhar o nadador na tela
    pool_pts = np.stack([traj.head_x, np.full(len(pts), lane_y)], axis=1)
    img = np.array(
        [
            cv2.perspectiveTransform(pool_pts[i].reshape(1, 1, 2), np.linalg.inv(H[i]))[0, 0]
            for i in range(len(pts))
        ]
    )
    df["head_img_x"], df["head_img_y"] = img[:, 0], img[:, 1]
    df.to_parquet(files.trajectory, index=False)

    start_t, start_conf, _ = detect_start_signal(paths)
    result = generate(race, traj, sig, start_t, start_conf)
    # eventos com posição recebem também o ponto na imagem (mesmo caminho dos cliques)
    out = []
    for e in result.events:
        if e.x_m is not None:
            p = cv2.perspectiveTransform(
                np.array([[[e.x_m, lane_y]]], float), np.linalg.inv(H[e.frame])
            )[0, 0]
            e = e.model_copy(update={"image_xy": (float(p[0]), float(p[1]))})
        out.append(e)
    return out, result.notes


def load_trajectory(paths: VideoPaths) -> Trajectory | None:
    import pandas as pd

    f = AnalysisFiles.of(paths).trajectory
    return Trajectory.from_frame(pd.read_parquet(f)) if f.exists() else None
