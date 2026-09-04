from __future__ import annotations

import uuid
from datetime import UTC, datetime

EPOCH_DATE = "1970-01-01"
EPOCH_DATETIME = "1970-01-01T00:00:00"


def new_load_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def with_metadata(rows, source_name: str, load_id: str, loaded_at: str):
    for row in rows:
        yield {
            **row,
            "_loaded_at": loaded_at,
            "_source_name": source_name,
            "_load_id": load_id,
        }
