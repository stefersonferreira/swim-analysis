"""Módulo 1 do pipeline: ingestão.

Entrada: vídeo original do celular. Saídas (pasta ingest/):
- proxy.mp4: H.264 todo-intra (um quadro-chave por quadro), largura até 1280 px,
  **mesmos quadros e mesmos tempos do original** (sem conversão de taxa), com áudio AAC.
  Todo-intra garante busca exata por quadro na revisão.
- frames.parquet: quadro -> PTS em segundos (relativo ao primeiro quadro). Celulares
  gravam com taxa variável; todo tempo do sistema vem desta tabela, nunca de i/fps.
- audio.wav (mono 48 kHz) e waveform.json (picos para desenhar a forma de onda).
- video_meta.json e poster.jpg.

ffmpeg/ffprobe são chamados como programas externos (não são ligados ao código).
"""

from __future__ import annotations

import json
import re
import subprocess
import wave
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

import numpy as np

from swimcv.contracts import VideoMeta
from swimcv.ingest.frames import write_frame_table
from swimcv.storage import VideoPaths

PROXY_MAX_WIDTH = 1280
MIN_FPS = 29.0  # 30 fps nominal, com folga para taxa variável
MIN_HEIGHT = 720
MAX_DURATION_S = 4 * 60
WAVEFORM_BINS_PER_S = 100
AUDIO_RATE = 48_000


class IngestError(Exception):
    """Vídeo recusado na validação; a mensagem é mostrada ao usuário."""


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} falhou: {proc.stderr[-2000:]}")
    return proc.stdout


def probe(path: Path) -> dict:
    out = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ]
    )
    return json.loads(out)


def _rotation(stream: dict) -> int:
    for sd in stream.get("side_data_list", []) or []:
        if "rotation" in sd:
            return int(round(float(sd["rotation"]))) % 360
    rot = (stream.get("tags") or {}).get("rotate")
    return int(rot) % 360 if rot else 0


def validate(info: dict, strict: bool = True) -> tuple[dict, dict | None, list[str]]:
    """Confere os requisitos obrigatórios. Devolve (vídeo, áudio, avisos)."""
    v = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
    a = next((s for s in info["streams"] if s.get("codec_type") == "audio"), None)
    if v is None:
        raise IngestError("O arquivo não tem faixa de vídeo.")
    warnings: list[str] = []
    rot = _rotation(v)
    w, h = int(v["width"]), int(v["height"])
    if rot in (90, 270):
        w, h = h, w
    fps = float(Fraction(v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1") or 0)
    dur = float(info["format"].get("duration") or v.get("duration") or 0)
    problems = []
    if fps < MIN_FPS:
        problems.append(f"taxa de {fps:.1f} fps (mínimo 30 fps; recomendado 60)")
    if min(w, h) < MIN_HEIGHT:
        problems.append(f"resolução {w}x{h} (mínimo 720p)")
    if dur > MAX_DURATION_S:
        problems.append(f"duração de {dur:.0f} s (máximo {MAX_DURATION_S} s)")
    if a is None:
        warnings.append(
            "Vídeo sem áudio: o sinal de largada terá de ser marcado à mão e a "
            "reação não será medida."
        )
    if problems and strict:
        raise IngestError("Vídeo recusado: " + "; ".join(problems) + ".")
    warnings += [f"Abaixo do requisito: {p}" for p in problems]
    return v, a, warnings


@lru_cache
def ffmpeg_version() -> tuple[int, int]:
    out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout
    m = re.search(r"ffmpeg version n?(\d+)\.(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else (7, 0)


def passthrough_args() -> list[str]:
    """Sem criar, descartar ou arredondar quadros, em qualquer ffmpeg de 4.4 a 7.x.

    - taxa: -fps_mode (5.1+) ou -vsync (antigo);
    - base de tempo do encoder igual à do original: "demux" (7+) ou -1 (até 6.x).
      Sem isso o encoder arredonda os tempos para 1/fps e perde a taxa variável.
    """
    v = ffmpeg_version()
    rate = ["-fps_mode", "passthrough"] if v >= (5, 1) else ["-vsync", "passthrough"]
    tb = ["-enc_time_base", "demux" if v >= (7, 0) else "-1"]
    return rate + tb


def make_proxy(src: Path, dst: Path, has_audio: bool) -> None:
    vf = f"scale='min({PROXY_MAX_WIDTH},iw)':-2:flags=bicubic,format=yuv420p"
    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(src),
        # passthrough + base de tempo do original: nenhum quadro criado, descartado ou
        # com o tempo arredondado (o padrão do encoder arredondaria para 1/fps).
        "-map",
        "0:v:0",
        *passthrough_args(),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-g",
        "1",
        "-keyint_min",
        "1",
        "-sc_threshold",
        "0",
        "-bf",
        "0",
    ]
    if has_audio:
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "128k"]
    cmd += ["-movflags", "+faststart", str(dst)]
    _run(cmd)


def extract_audio(src: Path, dst: Path) -> None:
    _run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(src),
            "-map",
            "0:a:0",
            "-ac",
            "1",
            "-ar",
            str(AUDIO_RATE),
            "-c:a",
            "pcm_s16le",
            str(dst),
        ]
    )


def compute_waveform(wav_path: Path, t0_offset: float = 0.0) -> dict:
    """Picos de amplitude (0..1) a cada 10 ms, para a linha do tempo da revisão."""
    with wave.open(str(wav_path), "rb") as w:
        rate = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    data /= 32768.0
    hop = rate // WAVEFORM_BINS_PER_S
    n = len(data) // hop
    peaks = np.abs(data[: n * hop]).reshape(n, hop).max(axis=1) if n else np.zeros(0)
    top = float(peaks.max()) if len(peaks) else 1.0
    peaks = peaks / top if top > 0 else peaks
    return {
        "bins_per_s": WAVEFORM_BINS_PER_S,
        "t0": t0_offset,
        "peaks": [round(float(p), 3) for p in peaks],
    }


def ingest_video(paths: VideoPaths, strict: bool = True) -> tuple[VideoMeta, list[str]]:
    """Roda a ingestão completa. Idempotente: refaz tudo a partir do original."""
    paths.ensure()
    src = paths.original()
    info = probe(src)
    v, a, warnings = validate(info, strict=strict)

    make_proxy(src, paths.proxy, has_audio=a is not None)
    table = write_frame_table(paths.proxy, paths.frames)
    n_src = _count_frames(src)
    if n_src != len(table):
        raise RuntimeError(f"proxy com {len(table)} quadros, original com {n_src}")

    pts = table["pts"].to_numpy()
    d = np.diff(pts)
    fps_measured = float(1.0 / np.median(d)) if len(d) else 0.0
    vfr = bool(len(d) and (d.max() - d.min()) > 0.25 / max(fps_measured, 1))

    pinfo = probe(paths.proxy)
    pv = next(s for s in pinfo["streams"] if s.get("codec_type") == "video")
    rot = _rotation(v)
    w, h = int(v["width"]), int(v["height"])
    if rot in (90, 270):
        w, h = h, w

    if a is not None:
        extract_audio(paths.proxy, paths.audio)
        paths.waveform.write_text(json.dumps(compute_waveform(paths.audio)))

    _run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(paths.proxy),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(paths.poster),
        ]
    )

    meta = VideoMeta(
        original_filename=src.name,
        width=w,
        height=h,
        proxy_width=int(pv["width"]),
        proxy_height=int(pv["height"]),
        rotation=rot,
        fps_nominal=float(Fraction(v.get("avg_frame_rate") or "0/1") or 0),
        fps_measured=fps_measured,
        variable_frame_rate=vfr,
        n_frames=len(table),
        duration_s=float(pts[-1] + (np.median(d) if len(d) else 0)),
        has_audio=a is not None,
        audio_sample_rate=AUDIO_RATE if a is not None else None,
    )
    paths.meta.write_text(meta.model_dump_json(indent=2))
    return meta, warnings


def _count_frames(path: Path) -> int:
    import av

    with av.open(str(path)) as c:
        s = c.streams.video[0]
        return sum(1 for p in c.demux(s) if p.pts is not None and p.size > 0)
