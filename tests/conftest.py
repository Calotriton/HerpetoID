"""Shared pytest configuration.

Qt-based tests (added in the GUI phase) run headlessly via the offscreen platform, so the suite needs
no display and works in CI.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
