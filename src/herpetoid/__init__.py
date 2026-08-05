"""HerpetoID — modular platform for non-invasive individual identification of wildlife.

Architecture (dependencies point inward to the Core):

* :mod:`herpetoid.api`            — the Qt-free plugin SDK (contracts + data types). No PySide6.
* :mod:`herpetoid.domain`         — entities / value objects / invariants. No Qt, no SQLAlchemy.
* :mod:`herpetoid.application`    — use-case services + ports.
* :mod:`herpetoid.infrastructure` — SQLAlchemy, image store, plugin loader, exporters, logging.
* :mod:`herpetoid.gui`            — PySide6 presentation layer (isolated; imported lazily).
* :mod:`herpetoid.plugins`        — first-party species modules and algorithms.

Project bundles and imported images are untrusted input; see ``SECURITY.md`` for the trust model.
"""

from __future__ import annotations

__all__ = ["API_VERSION", "__version__"]

#: Application version.
__version__ = "0.1.0"

#: Version of the plugin SDK contract (:class:`herpetoid.api.SpeciesModule` /
#: :class:`herpetoid.api.IdentificationAlgorithm`). Bumped only on breaking changes to
#: :mod:`herpetoid.api`. Plugins declare, via their descriptor, the ``api_version`` they target so the
#: registry can warn about incompatibilities.
API_VERSION = "1.0"
