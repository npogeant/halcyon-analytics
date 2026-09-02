from __future__ import annotations

import os

RAW_DIR = "data/raw"
DUCKDB_PATH = os.environ.get("DLT_DUCKDB_PATH", "data/halcyon.duckdb")
DATASET_NAME = "raw"
PIPELINE_NAME = "halcyon_relational"
