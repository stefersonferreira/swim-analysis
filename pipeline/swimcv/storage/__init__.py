"""Armazenamento atrás de uma interface: pasta local na etapa 1, S3 na etapa 2.

O pipeline só conhece caminhos lógicos por vídeo (VideoPaths). A troca para S3 entra
na etapa 2 sem mudar os módulos.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VideoPaths:
    root: Path

    @classmethod
    def for_video(cls, data_dir: str | Path, video_id: str) -> "VideoPaths":
        p = Path(data_dir) / "videos" / video_id
        return cls(root=p)

    def ensure(self) -> "VideoPaths":
        (self.root / "ingest").mkdir(parents=True, exist_ok=True)
        return self

    def original(self, suffix: str = "") -> Path:
        if suffix:
            return self.root / f"original{suffix}"
        found = sorted(self.root.glob("original.*"))
        if not found:
            raise FileNotFoundError(f"vídeo original não encontrado em {self.root}")
        return found[0]

    @property
    def meta(self) -> Path:
        return self.root / "ingest" / "video_meta.json"

    @property
    def frames(self) -> Path:
        return self.root / "ingest" / "frames.parquet"

    @property
    def proxy(self) -> Path:
        return self.root / "ingest" / "proxy.mp4"

    @property
    def audio(self) -> Path:
        return self.root / "ingest" / "audio.wav"

    @property
    def waveform(self) -> Path:
        return self.root / "ingest" / "waveform.json"

    @property
    def poster(self) -> Path:
        return self.root / "ingest" / "poster.jpg"
