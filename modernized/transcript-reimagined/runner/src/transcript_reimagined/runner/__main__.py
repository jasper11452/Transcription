"""``python -m transcript_reimagined.runner`` —— 等价于 ``transcript-run``。"""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
