"""Guard tests: what the plugin SDK is allowed to pull in.

Importing ``herpetoid.api`` in a fresh interpreter must not import PySide6, so plugins stay lightweight
and unit-testable without a Qt environment. It must not import OpenCV either — the SDK proper is pure
Python + NumPy, and the OpenCV-backed helpers live in ``herpetoid.api.preprocessing``, which a module
imports explicitly when it wants them. Run in a subprocess for a clean module table.
"""

from __future__ import annotations

import subprocess
import sys


def _import_leaks(module: str, forbidden: str) -> bool:
    code = f"import {module}, sys; sys.exit(1 if {forbidden!r} in sys.modules else 0)"
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).returncode != 0


def test_api_import_does_not_import_pyside6() -> None:
    assert not _import_leaks("herpetoid.api", "PySide6"), (
        "importing herpetoid.api must not import PySide6"
    )


def test_api_import_does_not_import_opencv() -> None:
    assert not _import_leaks("herpetoid.api", "cv2"), (
        "herpetoid.api must stay pure Python + NumPy; OpenCV helpers belong to "
        "herpetoid.api.preprocessing, which plugins import explicitly"
    )


def test_preprocessing_helpers_are_still_qt_free() -> None:
    assert not _import_leaks("herpetoid.api.preprocessing", "PySide6")
