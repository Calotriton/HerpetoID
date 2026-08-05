"""Console entry point for the HerpetoID desktop application.

Launches the PySide6 GUI. If PySide6 is missing (a core-only install), the command degrades
gracefully and reports that the Qt-free core and plugin SDK are still usable programmatically.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Launch the desktop GUI, or report status if the Qt layer is unavailable."""
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        from herpetoid.gui.app import run
    except ModuleNotFoundError:
        print(
            "HerpetoID core is installed and importable, but the desktop GUI could not be loaded "
            "(PySide6 is not available). Core services, the plugin registry, and the plugin SDK "
            "(`herpetoid.api`) are usable programmatically. Install with: pip install PySide6"
        )
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
