"""Console entry point for the HerpetoID desktop application.

The GUI (PySide6) is introduced in a later phase. Until then this keeps the installed ``herpetoid``
command wired end-to-end and degrades gracefully, reporting that the core is importable.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Launch the desktop GUI, or report status if the GUI layer is not yet available."""
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        from herpetoid.gui.app import run
    except ModuleNotFoundError:
        print(
            "HerpetoID core is installed and importable. The desktop GUI is not available yet "
            "(added in the GUI phase). Core services, the plugin registry, and the plugin SDK "
            "(`herpetoid.api`) are usable programmatically."
        )
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
