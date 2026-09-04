from __future__ import annotations

import glob
import json
import logging
import re
from pathlib import Path

import dlt
import pyarrow as pa

from . import config
from .common import EPOCH_DATE, new_load_id, now_iso

logger = logging.getLogger("ingestion.web_events")

_PARTITION_RE = re.compile(r"dt=(\d{4}-\d{2}-\d{2})")

_COLUMNS = [
    "event_id",
    "customer_id",
    "session_id",
    "event_type",
    "event_at",
    "product_id",
    "url",
    "channel",
    "device",
    "geo",
]


def _partition_date(path: str) -> str:
    match = _PARTITION_RE.search(path)
    if not match:
        raise ValueError(f"could not parse partition date from path: {path}")
    return match.group(1)


def _read_partition_as_table(path: str, load_id: str, loaded_at: str) -> pa.Table:
    # Columnar, not row-by-row: dlt normalizes an arrow table via its fast
    # path (no per-row Python dict typing/coercion), which is what makes
    # ~5M events tractable here -- the row-by-row dict version of this
    # resource took over 6 minutes; this reads and loads the same data in a
    # fraction of that.
    partition_date = _partition_date(path)
    columns: dict[str, list] = {name: [] for name in _COLUMNS}
    campaign_values: list[str | None] = []
    has_campaign_field = False

    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            event = json.loads(line)
            for name in _COLUMNS:
                if name == "geo":
                    columns["geo"].append(json.dumps(event["geo"]))
                else:
                    columns[name].append(event.get(name))
            if "utm_campaign" in event:
                has_campaign_field = True
            campaign_values.append(event.get("utm_campaign"))

    n = len(columns["event_id"])
    if has_campaign_field:
        # Only added when the source data actually carries the key -- a file
        # entirely before the schema-change date has no utm_campaign column
        # at all here, matching the source exactly, rather than a synthetic
        # all-null column dlt can't infer a type from.
        columns["utm_campaign"] = campaign_values
    columns["_partition_date"] = [partition_date] * n
    columns["_loaded_at"] = [loaded_at] * n
    columns["_source_name"] = ["web_events"] * n
    columns["_load_id"] = [load_id] * n
    return pa.table(columns)


def _read_partitions(load_id: str, loaded_at: str):
    pattern = f"{config.RAW_DIR}/web_events/dt=*/events.jsonl"
    for path in sorted(glob.glob(pattern)):
        yield _read_partition_as_table(path, load_id, loaded_at)


@dlt.source(name="halcyon_web_events")
def halcyon_web_events_source(load_id: str, loaded_at: str):
    # `geo` stays a single JSON column rather than being flattened into
    # geo__country: it's an open-ended attribute bag with no fixed shape yet
    # (AE-05's nested-field decision). `channel`/`device` are NOT nested here
    # even though they're also event attributes -- they're already documented
    # top-level dimensions in the bus matrix (docs/data-model.md), so nesting
    # them would silently break that design.
    @dlt.resource(
        name="web_events",
        write_disposition="append",
        primary_key="event_id",
        columns={"geo": {"data_type": "json"}},
        schema_contract={"columns": "evolve", "data_type": "freeze"},
        max_table_nesting=0,
    )
    def web_events(
        cursor=dlt.sources.incremental("_partition_date", initial_value=EPOCH_DATE),  # noqa: B008 -- dlt's documented incremental pattern
    ):
        # Cursor is the file's arrival/partition date, never `event_at`. The
        # generator's late-arriving defect writes events with an event_at
        # 1-3 days *earlier* than the partition they land in; using event_at
        # as the incremental cursor would make dlt's incremental range
        # (monotonically advancing) skip re-scanning a day whose late events
        # already pushed the watermark past them -- the exact bug the "event
        # time vs ingestion time" distinction this issue is about exists to
        # prevent. Partition date only ever advances forward one real file at
        # a time, so it's safe as an extraction checkpoint regardless of what
        # event_at says.
        yield from _read_partitions(load_id, loaded_at)

    return (web_events,)


def _log_schema_changes(load_info) -> None:
    for package in load_info.load_packages:
        update = package.schema_update.get("web_events")
        if not update:
            continue
        new_columns = sorted(update.get("columns", {}).keys())
        if new_columns:
            logger.info(
                "schema evolution: raw.web_events gained column(s) %s (load_id=%s)",
                new_columns,
                package.load_id,
            )


def run(full_refresh: bool = False):
    load_id = new_load_id()
    loaded_at = now_iso()

    pipeline = dlt.pipeline(
        pipeline_name=config.WEB_EVENTS_PIPELINE_NAME,
        destination=dlt.destinations.duckdb(credentials=config.DUCKDB_PATH),
        dataset_name=config.DATASET_NAME,
    )
    source = halcyon_web_events_source(load_id=load_id, loaded_at=loaded_at)
    load_info = pipeline.run(source, refresh="drop_data" if full_refresh else None)
    _log_schema_changes(load_info)
    return load_info
