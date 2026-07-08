"""Application layer: use-case services and ports.

Depends on the domain and the plugin SDK (:mod:`herpetoid.api`) plus abstract ports; it never imports
Qt or SQLAlchemy directly (those live in the infrastructure and presentation layers).
"""

from __future__ import annotations
