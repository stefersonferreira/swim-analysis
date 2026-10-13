import json
import random
import shutil

import numpy as np
import pytest

from swimcv.ingest import FrameReader, IngestError, ingest_video, read_frame_table
from swimcv.storage import VideoPaths
from tests.conftest import REFERENCE_VIDEO, decode_index, make_vfr_video

pytestmark = pytest.mark.video


@pytest.fixture(scope="module")
def vfr_ingested(tmp_path_factory, has_ffmpeg):
    data = tmp_path_factory.mktemp("data")
    paths = VideoPaths.for_video(data, "vfr").ensure()
    make_vfr_video(paths.original(".mp4"))
    meta, warnings = ingest_video(paths)
    return paths, meta, warnings


def test_proxy_keeps_every_frame_and_its_time(vfr_ingested):
    paths, meta, _ = vfr_ingested
    table = read_frame_table(paths.frames)
    assert meta.n_frames == 90 == len(table)
    expected = [(n + 0.3 * np.sin(n)) / 30 for n in range(90)]
    assert np.allclose(table["pts"], np.array(expected) - expected[0], atol=1e-3)
    assert meta.variable_frame_rate is True
    assert np.all(np.diff(table["pts"]) > 0)


def test_frame_reader_returns_exact_frame(vfr_ingested):
    paths, _, _ = vfr_ingested
    reader = FrameReader(paths.proxy, read_frame_table(paths.frames))
    rng = random.Random(7)
    asked = [rng.randrange(reader.n_frames) for _ in range(100)] + [0, 89, 45, 44, 46]
    for n in asked:
        assert decode_index(reader.bgr(n)) == n
    reader.close()


def test_audio_and_waveform(vfr_ingested):
    paths, meta, warnings = vfr_ingested
    assert meta.has_audio and paths.audio.exists()
    wf = json.loads(paths.waveform.read_text())
    peaks = np.array(wf["peaks"])
    loud = np.flatnonzero(peaks > 0.5) / wf["bins_per_s"]
    assert loud.size and abs(loud[0] - 1.0) < 0.05  # bipe em 1,0 s
    assert not warnings


def test_low_resolution_is_rejected(tmp_path, has_ffmpeg):
    import subprocess

    paths = VideoPaths.for_video(tmp_path, "low").ensure()
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=30:duration=1",
            str(paths.original(".mp4")),
        ],
        check=True,
    )
    with pytest.raises(IngestError, match="720p"):
        ingest_video(paths)


@pytest.mark.skipif(not REFERENCE_VIDEO.exists(), reason="vídeo de referência ausente")
def test_reference_video(tmp_path, has_ffmpeg):
    paths = VideoPaths.for_video(tmp_path, "ref").ensure()
    shutil.copy(REFERENCE_VIDEO, paths.original(".mp4"))
    meta, _ = ingest_video(paths)
    assert meta.n_frames == 995
    assert meta.fps_measured == pytest.approx(30, abs=0.1)
    assert (meta.proxy_width, meta.proxy_height) == (1280, 720)
