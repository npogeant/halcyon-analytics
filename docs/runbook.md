# Runbook

Operational procedures for this pipeline. Grows with later issues (`AE-25` pipeline resilience, `AE-26`
alerting, `AE-30` incident postmortems); only the source-staleness section exists so far (`AE-08`).

## Source staleness

`dbt source freshness` runs as part of `make build`, before `dbt build`. Thresholds are declared per table
in `transform/models/staging/sources.yml`, each with a one-line justification for why that source's SLA is
what it is — see that file for the full table-by-table list rather than duplicating it here, since the
justification and the threshold living apart would drift.

### What actually happens on a breach

- **`WARN`** (past `warn_after`, not yet `error_after`): `dbt source freshness` exits `0`. `make build`
  continues into `dbt build` normally. Nothing blocks; the warning is visible in the command's own output
  only.
- **`ERROR`** (past `error_after`): `dbt source freshness` exits `1`. `make build` aborts *before* `dbt
  build` ever runs — verified directly during `AE-08`: deliberately backdating `raw.payments._loaded_at`
  produces `ERROR STALE` and a `make: *** [build] Error 1` abort, with no model build attempted.

### Who to contact, and how

This is a solo portfolio project, not a team with an on-call rotation — so today, "who to contact" is
whoever runs `make build` and reads its output; there's no other channel yet. That's an honest limitation,
not a design choice: `AE-26` ("alerting that a human would actually act on") is where this gets routed
somewhere other than a terminal. Until then, a stale source is only noticed by someone actually running the
pipeline and seeing the failure — there's no push notification, no dashboard, nothing watching in the
background. This section should be revisited once `AE-26` lands.

### Diagnosing why a source is stale

1. Run `uv run dbt source freshness --project-dir transform --profiles-dir transform` directly (outside
   `make build`) to see every source's status at once, not just the one that first failed.
2. Check when each table was actually last loaded:
   ```sql
   select max(cast(_loaded_at as timestamptz)) from raw.<table>;
   ```
   (via `make shell`.)
3. Most likely causes, in order of how often they've actually happened while building this project:
   - **Ingestion just hasn't been run recently.** The straightforward case — run `make ingest`.
   - **This dataset is static and deterministic** (`AE-02`'s generator always produces the same fixed
     history), so once a table has been fully loaded once, a *plain* `make ingest` is a permanent no-op —
     there's never new data past the incremental cursor for it to find. If `_loaded_at` needs to actually
     advance, use `uv run python -m ingestion --full-refresh` (what `make demo` always does), not plain
     `make ingest`.
   - **A crashed or killed pipeline run left some tables loaded and others not.** Seen directly during
     `AE-08`'s own testing: an interrupted run left `customers`/`order_items`/`payments` empty while
     `orders`/`refunds`/etc. had full data, all sharing one `_loaded_at` — because the crash happened
     mid-*load*, after extraction had already staged a complete package on disk. Re-running the affected
     source (`--source relational` or `--source web_events`) resumes and finishes that staged package
     automatically; this is `ingestion/README.md`'s crash-safety guarantee working as intended, not data
     loss. If you need a guaranteed-fresh timestamp rather than just resuming, pass `--full-refresh`.

### Should a stale source block the build?

Yes, for anything past `error_after` — that's the entire point of the distinction from `warn_after`. A
`WARN` is a heads-up that doesn't justify blocking correct-but-slightly-behind data from reaching staging;
an `ERROR` means the data is stale enough that building on top of it would produce numbers nobody should
trust, so the build stopping *is* the correct, intended behavior, not a failure to work around.
