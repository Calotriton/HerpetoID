"""Shared pytest configuration.

Qt-based tests run headlessly via the offscreen platform, so the suite needs no display and works in
CI (see .github/workflows/ci.yml).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
