"""Gerador de prova sintética com verdade conhecida.

Desenha uma piscina vista de cima (texturas, cordas, marcas), um nadador na raia-alvo com
fases reais (bloco, voo, submerso, nado, virada olímpica, chegada), respingos a cada entrada
de braço, um nadador "intruso" na raia vizinha e projeta tudo numa câmera em perspectiva,
opcionalmente acompanhando o nadador (pan). Também gera o áudio com bipe de largada.

Usado nos testes do rastreamento e dos eventos automáticos e no teste de ponta a ponta.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

PX_PER_M = 24  # textura vista de cima
POOL_L = 25.0
LANES = 8
LANE_W = 2.5
POOL_W = LANES * LANE_W
OUT_W, OUT_H = 1280, 720
FPS = 30


@dataclass
class Truth:
    start_t: float = 1.0
    feet_off_t: float = 1.70
    entry_t: float = 2.05
    entry_x: float = 3.5
    breakout_t: float = 5.0
    breakout_x: float = 10.0
    v1: float = 2.0  # m/s no nado da 1ª piscina
    wall_t: float = 0.0  # calculado
    pushoff_t: float = 0.0
    breakout2_t: float = 0.0
    breakout2_d: float = 7.0
    v2: float = 1.9
    finish_t: float = 0.0
    arm_period: float = 0.48  # crawl: intervalo entre entradas de braço (ciclo = 0,96 s)
    lane: int = 4
    strokes: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.wall_t = self.breakout_t + (POOL_L - self.breakout_x) / self.v1
        self.pushoff_t = self.wall_t + 0.35
        self.breakout2_t = self.pushoff_t + 2.2
        self.finish_t = self.breakout2_t + (POOL_L - self.breakout2_d) / self.v2
        s: list[float] = []
        t = self.breakout_t + 0.15
        while t < self.wall_t - 0.6:
            s.append(round(t, 4))
            t += self.arm_period
        t = self.breakout2_t + 0.15
        while t < self.finish_t - 0.3:
            s.append(round(t, 4))
            t += self.arm_period
        self.strokes = s

    @property
    def lane_y(self) -> float:
        return (self.lane - 0.5) * LANE_W

    def head_x(self, t: float) -> float:
        """Posição da cabeça (m, a partir da parede de saída)."""
        if t < self.feet_off_t:
            return 0.0
        if t < self.entry_t:  # voo
            a = (t - self.feet_off_t) / (self.entry_t - self.feet_off_t)
            return a * self.entry_x
        if t < self.breakout_t:  # submerso, desacelerando
            a = (t - self.entry_t) / (self.breakout_t - self.entry_t)
            return self.entry_x + (self.breakout_x - self.entry_x) * (1 - (1 - a) ** 1.4)
        if t < self.wall_t:
            return min(POOL_L - 0.3, self.breakout_x + self.v1 * (t - self.breakout_t))
        if t < self.pushoff_t:  # cambalhota
            return POOL_L - 0.3 - 0.9 * np.sin(np.pi * (t - self.wall_t) / 0.35)
        if t < self.breakout2_t:
            a = (t - self.pushoff_t) / (self.breakout2_t - self.pushoff_t)
            return POOL_L - self.breakout2_d * (1 - (1 - a) ** 1.3)
        if t < self.finish_t:
            return POOL_L - self.breakout2_d - self.v2 * (t - self.breakout2_t)
        return 0.0

    def phase(self, t: float) -> str:
        if t < self.feet_off_t:
            return "block"
        if t < self.entry_t:
            return "flight"
        if t < self.breakout_t:
            return "underwater"
        if t < self.wall_t:
            return "swim"
        if t < self.breakout2_t:
            return "underwater"
        if t < self.finish_t:
            return "swim"
        return "finish"


def pool_to_canvas() -> np.ndarray:
    """Homografia piscina (m) -> tela da câmera parada: vista oblíqua da borda lateral."""
    src = np.float32([[0, 0], [POOL_L, 0], [POOL_L, POOL_W], [0, POOL_W]])
    # raia 1 (y=0) perto da câmera, embaixo; a raia 8 longe, em cima
    dst = np.float32([[-60, 700], [1340, 700], [1050, 250], [230, 250]])
    return cv2.getPerspectiveTransform(src, dst)


def camera_pan(t: float, moving: bool, truth: Truth) -> np.ndarray:
    """Movimento da câmera na imagem (acompanha o nadador)."""
    if not moving:
        return np.eye(3)
    x = truth.head_x(t)
    dx = -(x - 12.5) * 14.0  # px
    dy = 8.0 * np.sin(t * 0.7)
    ang = np.deg2rad(0.6 * np.sin(t * 0.5))
    c, s = np.cos(ang), np.sin(ang)
    cx, cy = OUT_W / 2, OUT_H / 2
    rot = np.array([[c, -s, cx - c * cx + s * cy], [s, c, cy - s * cx - c * cy], [0, 0, 1]])
    return np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]]) @ rot


def _background(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    bg = np.full((OUT_H + 400, OUT_W + 800, 3), (70, 80, 95), np.uint8)
    for _ in range(500):  # arquibancada, bandeiras, pessoas: textura para o rastreio da câmera
        x, y = rng.integers(0, bg.shape[1]), rng.integers(0, 420)
        w, h = rng.integers(8, 50), rng.integers(8, 60)
        col = tuple(int(v) for v in rng.integers(20, 250, 3))
        cv2.rectangle(bg, (int(x), int(y)), (int(x + w), int(y + h)), col, -1)
    return bg


def _pool_texture(seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Água + cordas vistas de cima. Devolve (textura, máscara de cordas)."""
    rng = np.random.default_rng(seed)
    h, w = int(POOL_W * PX_PER_M), int(POOL_L * PX_PER_M)
    water = np.zeros((h, w, 3), np.float32)
    water[:] = (205, 165, 70)  # BGR azul-piscina
    lines = rng.normal(0, 1, (h // 8, w // 8)).astype(np.float32)
    lines = cv2.resize(cv2.GaussianBlur(lines, (0, 0), 2), (w, h))
    water += lines[..., None] * np.float32([10, 12, 8])
    # faixas escuras no fundo (centro de cada raia)
    for k in range(LANES):
        yc = int((k + 0.5) * LANE_W * PX_PER_M)
        cv2.line(water, (int(2 * PX_PER_M), yc), (int(23 * PX_PER_M), yc), (120, 90, 40), 5)
    ropes = np.zeros((h, w), np.uint8)
    for k in range(LANES + 1):
        y = int(k * LANE_W * PX_PER_M)
        for x0 in range(0, w, 6):
            xm = x0 / PX_PER_M
            col = (
                (40, 40, 200)
                if (xm < 5 or xm > 20)
                else ((240, 240, 240) if (x0 // 6) % 2 else (130, 60, 20))
            )
            cv2.line(water, (x0, y), (x0 + 5, y), col, 3)
            cv2.line(ropes, (x0, y), (x0 + 5, y), 255, 3)
    return water, ropes


def render(
    path: Path,
    truth: Truth | None = None,
    moving: bool = False,
    seconds: float | None = None,
    seed: int = 0,
    intruder: bool = True,
) -> Truth:
    truth = truth or Truth()
    dur = seconds or (truth.finish_t + 1.5)
    n = int(dur * FPS)
    rng = np.random.default_rng(seed)
    base, _ = _pool_texture(seed)
    bg = _background(seed)
    H0 = pool_to_canvas()
    S = np.diag([PX_PER_M, PX_PER_M, 1.0])  # piscina (m) -> textura (px)
    tex_to_canvas = H0 @ np.linalg.inv(S)
    off = np.array([[1, 0, 400], [0, 1, 400], [0, 0, 1]], float)  # fundo maior que a tela
    raw = path.with_suffix(".raw.mp4")
    proc = subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{OUT_W}x{OUT_H}",
            "-r",
            str(FPS),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(raw),
        ],
        stdin=subprocess.PIPE,
    )
    splashes: list[tuple[float, float, float, float]] = []  # (t, x, y, raio)
    for i in range(n):
        t = i / FPS
        tex = base.copy()
        ripple = rng.normal(0, 1, (tex.shape[0] // 6, tex.shape[1] // 6)).astype(np.float32)
        ripple = cv2.resize(cv2.GaussianBlur(ripple, (0, 0), 1.2), (tex.shape[1], tex.shape[0]))
        tex += ripple[..., None] * 9
        swimmers = [(truth, 1.0)]
        if intruder:
            other = Truth(lane=truth.lane + 1, v1=1.75, v2=1.7, breakout_x=8.5, arm_period=0.55)
            swimmers.append((other, 1.0))
        for sw, _ in swimmers:
            ph = sw.phase(t)
            hx = sw.head_x(t)
            d = 1 if (t < sw.wall_t) else -1
            if ph in ("block", "finish"):
                continue
            body_c = hx - d * 0.85
            alpha = 0.25 if ph == "underwater" else (0.0 if ph == "flight" else 0.7)
            if alpha > 0:
                ov = tex.copy()
                cv2.ellipse(
                    ov,
                    (int(body_c * PX_PER_M), int(sw.lane_y * PX_PER_M)),
                    (int(0.9 * PX_PER_M), int(0.25 * PX_PER_M)),
                    0,
                    0,
                    360,
                    (60, 50, 40),
                    -1,
                )
                tex = cv2.addWeighted(ov, alpha, tex, 1 - alpha, 0)
            if abs(t - sw.entry_t) < 1.0 / FPS:
                splashes.append((t, sw.entry_x, sw.lane_y, 1.0))
            for st in sw.strokes:
                if abs(t - st) < 0.5 / FPS:
                    side = 0.3 if (sw.strokes.index(st) % 2) else -0.3
                    splashes.append((t, hx + d * 0.35, sw.lane_y + side, 0.55))
            if ph == "swim":  # pernada: espuma contínua atrás do corpo
                kx = hx - d * 1.9
                cv2.ellipse(
                    tex,
                    (int(kx * PX_PER_M), int(sw.lane_y * PX_PER_M)),
                    (int(0.45 * PX_PER_M), int(0.18 * PX_PER_M)),
                    0,
                    0,
                    360,
                    (225, 225, 225),
                    -1,
                )
        for t0, sx, sy, r in splashes:
            age = t - t0
            if 0 <= age < 0.35:
                a = 1 - age / 0.35
                rr = int(r * (0.6 + age) * PX_PER_M)
                ov = tex.copy()
                cv2.circle(ov, (int(sx * PX_PER_M), int(sy * PX_PER_M)), rr, (250, 250, 250), -1)
                tex = cv2.addWeighted(ov, 0.85 * a, tex, 1 - 0.85 * a, 0)
        tex8 = np.clip(tex, 0, 255).astype(np.uint8)
        canvas = bg.copy()
        Hc = off @ tex_to_canvas
        warped = cv2.warpPerspective(tex8, Hc, (canvas.shape[1], canvas.shape[0]))
        mask = cv2.warpPerspective(
            np.full(tex8.shape[:2], 255, np.uint8), Hc, (canvas.shape[1], canvas.shape[0])
        )
        canvas[mask > 0] = warped[mask > 0]
        P = camera_pan(t, moving, truth) @ np.linalg.inv(off)
        frame = cv2.warpPerspective(canvas, P, (OUT_W, OUT_H), borderValue=(60, 60, 60))
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    assert proc.wait() == 0
    _mux_audio(raw, path, dur, truth.start_t)
    raw.unlink()
    return truth


def _mux_audio(video: Path, out: Path, dur: float, beep_t: float) -> None:
    ms = int(beep_t * 1000)
    af = (
        f"anoisesrc=d={dur}:c=pink:a=0.05[n];sine=f=1200:d=0.25,adelay={ms}|{ms},"
        f"apad=whole_dur={dur}[b];[n][b]amix=inputs=2:normalize=0"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-filter_complex",
            af,
            "-map",
            "0:v",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(out),
        ],
        check=True,
    )


def frame_homography_pool_to_image(t: float, moving: bool, truth: Truth) -> np.ndarray:
    """Verdade da câmera: piscina (m) -> imagem (px) no instante t."""
    return camera_pan(t, moving, truth) @ pool_to_canvas()


def anchor_points(t: float, moving: bool, truth: Truth) -> list[dict]:
    """Cliques de calibração 'perfeitos' (cordas x marcas) visíveis no quadro do instante t."""
    H = frame_homography_pool_to_image(t, moving, truth)
    pts = []
    for rope in (0, 2, 4, 6, 8):
        for xm in (0.0, 5.0, 10.0, 15.0, 20.0, 25.0):
            p = cv2.perspectiveTransform(np.float32([[[xm, rope * LANE_W]]]), H)[0, 0]
            if 5 < p[0] < OUT_W - 5 and 5 < p[1] < OUT_H - 5:
                pts.append({"image_xy": [float(p[0]), float(p[1])], "pool_xy": [xm, rope * LANE_W]})
    return pts
