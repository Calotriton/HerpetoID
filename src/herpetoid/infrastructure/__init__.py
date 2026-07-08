"""Infrastructure layer: adapters for the outside world.

SQLAlchemy persistence, the image store, plugin discovery, exporters, settings storage and logging.
Implements ports declared by the application layer; nothing here is imported by the domain.
"""

from __future__ import annotations
