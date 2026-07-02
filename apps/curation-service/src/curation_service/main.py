"""Curation Service — worker/library service (§6.1).

No public HTTP port at this stage; exposes a service factory used by other apps
and by the orchestration pipeline.
"""

from __future__ import annotations

from kg_common import get_logger

_log = get_logger("curation-service")


class CurationService:
    """Placeholder service object; concrete logic lives in sibling modules."""

    name = "curation-service"

    def health(self) -> dict[str, str]:
        return {"status": "ok", "service": self.name}


def create_app() -> CurationService:
    return CurationService()
