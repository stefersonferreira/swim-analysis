"""MP4 com a sobreposição: desenho de um quadro e gravação com ffmpeg."""

import shutil
import subprocess

import av
import numpy as np
import pytest
from PIL import Image

from swimcv.metrics import compute_metrics
from swimcv.overlay import build_timeline
from swimcv.overlay.render import END_HOLD_S, Painter, render_mp4
from tests.unit.test_metrics import reference_free_50m


def timeline(**kw):
    race, evs = reference_free_50m()
    return build_timeline(
        race, evs, compute_metrics(race, evs), title="50 livre", width=640, height=360, **kw
    )


def test_draw_changes_pixels_where_expected():
    tl = timeline()
    frame = Image.new("RGB", (640, 360), (40, 120, 180))
    p = Painter(tl, 640, 360)
    out = np.asarray(p.draw(frame, 8.0), int)
    base = np.asarray(frame, int)
    diff = np.abs(out - base).sum(axis=2) > 30
    assert diff[10:60, 10:110].mean() > 0.5  # cartão do relógio
    assert diff[10:60, -100:-10].mean() > 0.5  # painel da piscina
    assert diff[180:250, 280:360].mean() < 0.05  # meio do quadro livre (sem nadador)
    # escala junto com o quadro: 2x maior desenha no mesmo lugar relativo
    big = np.asarray(Painter(tl, 1280, 720).draw(frame.resize((1280, 720)), 8.0), int)
    assert np.abs(big[::2, ::2] - out).mean() < 12


def test_summary_card_at_end():
    tl = timeline()
    frame = Image.new("RGB", (640, 360), (40, 120, 180))
    out = np.asarray(Painter(tl, 640, 360).draw(frame, 30.0, force_summary=True), int)
    centre = out[150:210, 260:380]
    assert centre.mean() < 80  # cartão escuro no centro


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg não instalado")
def test_render_mp4_with_audio_and_end_card(tmp_path):
    src = tmp_path / "proxy.mp4"
    wav = tmp_path / "audio.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=3",
         "-c:v", "libx264", "-g", "1", "-pix_fmt", "yuv420p", str(src)],
        check=True,
    )  # fmt: skip
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", str(wav)],
        check=True,
    )
    pts = np.arange(90) / 30
    seen = []
    out = render_mp4(
        src, pts, timeline(), tmp_path / "o.mp4", audio=wav, fps=30, progress=seen.append
    )
    with av.open(str(out)) as c:
        v = c.streams.video[0]
        n = sum(1 for _ in c.decode(v))
        assert (v.codec_context.width, v.codec_context.height) == (640, 360)
        assert len(c.streams.audio) == 1
    assert n == 90 + int(END_HOLD_S * 30)
    assert seen[-1] == 1.0


def test_portrait_video_uses_bigger_panels():
    """Celular em pé: painéis em 2,2% da largura por unidade, como o --u da tela."""
    from swimcv.overlay.render import PORTRAIT_SCALE

    tl = timeline()
    land = Painter(tl, 1280, 720)
    port = Painter(tl, 720, 1280)
    assert port.u == pytest.approx(7.2 * PORTRAIT_SCALE)
    assert land.u == pytest.approx(12.8)
    frame = Image.new("RGB", (720, 1280), (40, 120, 180))
    out = np.asarray(port.draw(frame, 8.0), int)
    diff = np.abs(out - np.asarray(frame, int)).sum(axis=2) > 30
    # cartão do relógio ocupa uma faixa larga no alto, sem sair do quadro
    assert diff[30:150, 30:250].mean() > 0.4
    assert not diff[:, -2:].all()
