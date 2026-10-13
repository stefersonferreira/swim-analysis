"""Tabela de quadros (PTS) e leitura exata de um quadro do proxy."""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

import av
import cv2
import numpy as np
import pandas as pd


def write_frame_table(proxy: Path, dst: Path) -> pd.DataFrame:
    """Quadro -> PTS (s), lido dos pacotes do proxy sem decodificar.

    O proxy é todo-intra e sem quadros B, então a ordem dos pacotes já é a ordem de
    exibição; ordenamos por PTS mesmo assim, por segurança.
    """
    with av.open(str(proxy)) as c:
        s = c.streams.video[0]
        tb = float(s.time_base)
        pts = sorted(p.pts for p in c.demux(s) if p.pts is not None and p.size > 0)
    if not pts:
        raise RuntimeError("proxy sem quadros")
    raw = np.asarray(pts, dtype=np.int64)
    df = pd.DataFrame(
        {
            "frame": np.arange(len(raw), dtype=np.int32),
            "pts_raw": raw,
            "pts": (raw - raw[0]) * tb,
        }
    )
    df.to_parquet(dst, index=False)
    return df


def read_frame_table(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


class FrameReader:
    """Decodifica o quadro N exato do proxy (busca por PTS num vídeo todo-intra)."""

    def __init__(self, proxy: Path, table: pd.DataFrame):
        self._container = av.open(str(proxy))
        self._stream = self._container.streams.video[0]
        self._stream.thread_type = "AUTO"
        self._pts_raw = table["pts_raw"].to_numpy()
        self._lock = threading.Lock()

    @property
    def n_frames(self) -> int:
        return len(self._pts_raw)

    def bgr(self, n: int) -> np.ndarray:
        if not 0 <= n < self.n_frames:
            raise IndexError(f"quadro {n} fora de 0..{self.n_frames - 1}")
        target = int(self._pts_raw[n])
        with self._lock:
            self._container.seek(target, stream=self._stream, backward=True, any_frame=False)
            for frame in self._container.decode(self._stream):
                if frame.pts is None or frame.pts < target:
                    continue
                if frame.pts != target:
                    raise RuntimeError(f"busca caiu no PTS {frame.pts}, esperado {target}")
                return frame.to_ndarray(format="bgr24")
        raise RuntimeError(f"quadro {n} não decodificado")

    def jpeg(self, n: int, quality: int = 88) -> bytes:
        ok, buf = cv2.imencode(".jpg", self.bgr(n), [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise RuntimeError("falha ao codificar JPEG")
        return buf.tobytes()

    def close(self) -> None:
        self._container.close()


class FrameReaderCache:
    """Mantém poucos leitores abertos (um por vídeo em revisão)."""

    def __init__(self, size: int = 4):
        self._size = size
        self._items: OrderedDict[str, FrameReader] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str, proxy: Path, table_path: Path) -> FrameReader:
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]
            reader = FrameReader(proxy, read_frame_table(table_path))
            self._items[key] = reader
            while len(self._items) > self._size:
                _, old = self._items.popitem(last=False)
                old.close()
            return reader

    def drop(self, key: str) -> None:
        with self._lock:
            r = self._items.pop(key, None)
            if r:
                r.close()
