from pydantic import BaseModel


class VideoMeta(BaseModel):
    """Metadados do vídeo, gravados pela ingestão em video_meta.json."""

    schema_version: int = 1
    original_filename: str
    width: int
    height: int
    proxy_width: int
    proxy_height: int
    rotation: int = 0
    fps_nominal: float
    fps_measured: float
    variable_frame_rate: bool
    n_frames: int
    duration_s: float
    has_audio: bool
    audio_sample_rate: int | None = None
