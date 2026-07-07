"""Guard test: the plugin SDK must never pull in a GUI framework.

Importing ``herpetoid.api`` in a fresh interpreter must not import PySide6, so plugins stay lightweight
and unit-testable without a Qt environment. Run in a subprocess for a clean module table.
"""

from __future__ import annotations

import subprocess
import sys


def test_api_import_does_not_import_pyside6() -> None:
    code = "import herpetoid.api, sys; sys.exit(1 if 'PySide6' in sys.modules else 0)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, "importing herpetoid.api must not import PySide6"
