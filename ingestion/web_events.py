from __future__ import annotations

import glob
import logging
import re

import dlt
import pyarrow as pa
import pyarrow.json as pa_json

from . import config
from .common import EPOCH_DATE, new_load_id, now_iso

logger = logging.getLogger("ingestion.web_events")

_PARTITION_RE = re.compile(r"dt=(\d{4}-\d{2}-\d{2})")

# The only type this pipeline forces: event_at must stay a raw string, not be
# auto-parsed into a timestamp. pyarrow's JSON reader otherwise infers
# `event_at` as timestamp[s] from the well-formed rows and silently collapses
# the naive-vs-UTC-suffixed distinction the generator injects on purpose
# (the exact defect AE-07's `to_utc()` macro exists to fix downstream) --
# that's ingestion making a business decision it isn't allowed to make.
# Every other field, including any field this code has never seen before, is
# picked up automatically (`unexpected_field_behavior="infer"`): no column
# allowlist to maintain, no code change needed if the source adds a field.
_PARSE_OPTIONS = pa_json.ParseOptions(
    explicit_schema=pa.schema([("event_at", pa.string())]),
    unexpected_field_behavior="infer",
)


def _partition_date(path: str) -> str:
    match = _PARTITION_RE.search(path)
    if not match:
        raise ValueError(f"could not parse partition date from path: {path}")
    return match.group(1)


def _read_partition_as_table(path: str, load_id: str, loaded_at: str) -> pa.Table:
    # pyarrow's native JSON reader, not per-line json.loads: the row-by-row
    # dict version of this resource took over 6 minutes to load ~5M events;
    # this reads and loads the same data in a small fraction of that, and
    # infers the schema directly from the file rather than a maintained list.
    table = pa_json.read_json(path, parse_options=_PARSE_OPTIONS)
    n = table.num_rows
    partition_date = _partition_date(path)
    return (
        table.append_column(
            "_partition_date", pa.array([partition_date] * n, type=pa.string())
        )
        .append_column("_loaded_at", pa.array([loaded_at] * n, type=pa.string()))
        .append_column("_source_name", pa.array(["web_events"] * n, type=pa.string()))
        .append_column("_load_id", pa.array([load_id] * n, type=pa.string()))
    )


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
    # them would silently break that design. dlt maps a pyarrow struct column
    # to its own `json` data type automatically; `max_table_nesting=0` is what
    # tells it to do that instead of flattening the struct into `geo__country`.
    @dlt.resource(
        name="web_events",
        write_disposition="append",
        primary_key="event_id",
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
