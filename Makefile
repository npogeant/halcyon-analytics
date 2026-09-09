.PHONY: setup seed ingest build test docs demo shell clean

setup:
	uv sync
	uv run pre-commit install
	uv run dbt deps --project-dir transform --profiles-dir transform

seed:
	uv run python -m generator

ingest:
	uv run python -m ingestion

build:
	uv run dbt build --project-dir transform --profiles-dir transform

test:
	uv run dbt test --project-dir transform --profiles-dir transform

docs:
	uv run dbt docs generate --project-dir transform --profiles-dir transform

demo: seed
	uv run python -m ingestion --full-refresh
	$(MAKE) build

shell:
	duckdb data/halcyon.duckdb

clean:
	rm -rf transform/target transform/dbt_packages data/*.duckdb data/*.duckdb.wal
	rm -rf ~/.dlt/pipelines/halcyon_relational ~/.dlt/pipelines/halcyon_web_events
