"""`transcript_reimagined.web` —— 传输层。"""

from __future__ import annotations

from .app import create_app
from .frontend import DIST_DIR, FRONTEND_DIR, ensure_frontend, validate_dist

__all__ = ["DIST_DIR", "FRONTEND_DIR", "create_app", "ensure_frontend", "validate_dist"]
