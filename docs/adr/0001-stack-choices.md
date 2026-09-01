# 0001 · Stack choices

## Status
Accepted

## Context
Halcyon Analytics needs a stack that is fully reproducible on a laptop, free to run, and close enough to
production tooling to be a credible portfolio piece.

## Decision
- **DuckDB** as the warehouse. In-process, no server to run, fast enough for the data volumes here, and
  swappable later for a cloud warehouse (see `0009-warehouse-portability.md`).
- **dbt** for transformation. Industry-standard, testable, self-documenting, and the closest match to how
  analytics engineering teams actually work.
- **dlt** for ingestion. Handles schema evolution and incremental loading with far less boilerplate than
  hand-rolled Python, without hiding the pipeline behind a GUI.
- **Dagster** for orchestration (introduced in M6). Asset-based scheduling maps directly onto dbt models,
  which is a better fit here than task-based DAGs.
- **uv** for Python dependency management. Fast, single lockfile, no separate virtualenv tooling to install.

## Rejected alternatives
- **Airflow**, for orchestration. Task-based DAGs fight a dbt-centric, asset-oriented project; it is also
  heavier to run and operate locally than the payoff justifies here.
- **Snowflake**, as the default warehouse. Real cost for a portfolio project with no paying users; DuckDB
  gets the same SQL surface and dbt workflow for free, and portability to a cloud warehouse is validated
  later rather than paid for from day one.
- **Orchestrating ingestion from inside dbt** (e.g. dbt-lite pre-hooks calling out to Python). Keeps
  ingestion and transformation as separate concerns with separate failure domains, which is the boundary a
  real platform needs.
- **Poetry**, for Python dependency management. uv is faster and needs no separate virtualenv step, at the
  cost of being newer and less battle-tested.
