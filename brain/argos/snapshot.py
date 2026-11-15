"""The one stored image: on escalation only, to the private `snapshots` store.

Called only by the brain's follow-up after an incident has escalated. One attempt, with the
time limit the brain sets, and no retry. If it fails, the incident keeps a null
`snapshot_path` and everything else goes ahead.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from argos import images
from argos.store import Store

BUCKET = "snapshots"


def snapshot_path(incident_id: str) -> str:
    return f"incidents/{incident_id}/snapshot.jpg"


def make_uploader(store: Store) -> Callable[[str, Any], str | None]:
    def upload(incident_id: str, frame: Any) -> str | None:
        data = images.jpeg(images.image_of(frame), max_side=1280, quality=85)
        path = snapshot_path(incident_id)
        store.upload(BUCKET, path, data, "image/jpeg")
        return path

    return upload
