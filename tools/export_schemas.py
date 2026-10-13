"""Exporta os contratos (Pydantic) como JSON Schema em spec/schemas/.

O CI roda este script e falha se o resultado diferir do que está no repositório:
mudou um contrato, tem que subir schema_version e commitar o esquema novo.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from swimcv import contracts as c  # noqa: E402

MODELS = {
    "race": c.RaceInfo,
    "event": c.Event,
    "metrics_report": c.MetricsReport,
    "calibration": c.Calibration,
    "pool_profile": c.PoolProfile,
    "video_meta": c.VideoMeta,
}


def main() -> None:
    out = ROOT / "spec" / "schemas"
    out.mkdir(parents=True, exist_ok=True)
    for name, model in MODELS.items():
        schema = model.model_json_schema()
        (out / f"{name}.schema.json").write_text(
            json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    print(f"{len(MODELS)} esquemas em {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
