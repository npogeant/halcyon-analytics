.PHONY: setup seed build test docs demo clean

setup:
	uv sync
	uv run pre-commit install

seed:
	uv run python -m generator

build:
	uv run dbt build --project-dir transform --profiles-dir transform

test:
	uv run dbt test --project-dir transform --profiles-dir transform

docs:
	uv run dbt docs generate --project-dir transform --profiles-dir transform

demo: seed build

clean:
	rm -rf transform/target transform/dbt_packages data/*.duckdb data/*.duckdb.wal
