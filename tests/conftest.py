import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

REFERENCE_VIDEO = Path(__file__).parent / "golden" / "reference_free_50yd.mp4"
BITS = 12
CELL = 48


def encode_index(n: int, w: int = 1280, h: int = 720) -> np.ndarray:
    """Quadro sintético com o próprio índice gravado em blocos preto/branco."""
    img = np.full((h, w, 3), 90, np.uint8)
    for b in range(BITS):
        on = (n >> b) & 1
        x0 = 20 + b * (CELL + 8)
        img[20 : 20 + CELL, x0 : x0 + CELL] = 255 if on else 0
    return img


def decode_index(img: np.ndarray) -> int:
    n = 0
    for b in range(BITS):
        x0 = 20 + b * (CELL + 8)
        if img[20 + 8 : 20 + CELL - 8, x0 + 8 : x0 + CELL - 8].mean() > 128:
            n |= 1 << b
    return n


def make_vfr_video(path: Path, n_frames: int = 90, audio: bool = True) -> None:
    """Vídeo 720p com taxa variável (PTS irregulares) e, opcionalmente, um bipe em 1,0 s."""
    raw = path.with_suffix(".nut")
    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        "1280x720",
        "-r",
        "30",
        "-i",
        "-",
    ]
    if audio:
        cmd += [
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=2000:duration=0.15,adelay=1000|1000,apad=whole_dur=3.5",
        ]
    cmd += [
        "-vf",
        "settb=1/90000,setpts='(N+0.3*sin(N))/30/TB'",
        "-fps_mode",
        "passthrough",
        "-enc_time_base",
        "1/90000",
        "-video_track_timescale",
        "90000",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-qp",
        "0",
        "-g",
        "15",
    ]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    cmd += [str(path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n_frames):
        proc.stdin.write(encode_index(i).tobytes())
    proc.stdin.close()
    assert proc.wait() == 0
    raw.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def has_ffmpeg():
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg não instalado")
