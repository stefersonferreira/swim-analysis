"""Transforma o fim de um log em anotações de erro do GitHub Actions.

Anotações aparecem na API e na página do CI mesmo quando o download de logs não está
disponível. Cada anotação leva até ~3.000 caracteres; usamos no máximo 9.
"""

import sys
from pathlib import Path

CHUNK = 3000
MAX_ANNOTATIONS = 9


def esc(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "").replace("\n", "%0A")


def main(path: str) -> None:
    text = Path(path).read_text(errors="replace") if Path(path).exists() else "(sem log)"
    tail = text[-CHUNK * MAX_ANNOTATIONS :]
    parts = [tail[i : i + CHUNK] for i in range(0, len(tail), CHUNK)]
    for n, part in enumerate(parts, 1):
        print(f"::error title=Log do CI ({n}/{len(parts)})::{esc(part)}")


if __name__ == "__main__":
    main(sys.argv[1])
