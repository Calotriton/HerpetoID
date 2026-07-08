"""Application layer: use-case services and ports.

Most of this layer depends only on the domain, the plugin SDK (:mod:`herpetoid.api`) and abstract
ports, and never imports Qt. The project-lifecycle composition (:mod:`.project_service`) is the one
place that wires concrete infrastructure adapters (database + image store) to open a project workspace.
"""

from __future__ import annotations
