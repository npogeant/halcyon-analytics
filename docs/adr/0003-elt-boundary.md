# 0003 · The ELT boundary

## Status
Accepted

## Context
"We do ELT, not ETL" is a claim most projects make and few actually enforce. Enforcing it means the
ingestion layer (`ingestion/`, `AE-04`/`AE-05`) contains **no business logic** — no currency conversion, no
filtering rows, no renaming to friendly names — because every one of those decisions, once baked into
extraction, can only be undone by re-extracting from the source. A transformation applied in dbt staging
(`AE-07`) can be redefined and rerun against data already sitting in `raw`; a transformation applied in
ingestion is gone unless the source system still has the original values to re-pull.

## Decision

**Ingestion is allowed to:**
- **Cast for storage**, where the cast prevents information loss rather than interpreting the data. The
  one example in this codebase: `web_events.event_at` is explicitly pinned to `string` in
  `ingestion/web_events.py`'s `ParseOptions`, overriding pyarrow's own auto-inference (which would
  otherwise silently parse it into a timestamp and erase the naive-vs-UTC-suffixed distinction the
  generator injects on purpose). This is a storage decision, not an interpretation of what the value
  *means* — the string is preserved exactly as the source sent it, just protected from an inference engine
  guessing a type for it. Compare with `AE-07`'s `to_utc()` macro, which *would* be forbidden here: deciding
  that a naive timestamp means UTC is a business rule about the data's meaning, and it happens in staging
  precisely so it's versioned, tested, and can be changed without re-ingesting.
- **Add load metadata.** Every raw table carries `_loaded_at`, `_source_name`, `_load_id` (`ingestion/common.py`,
  `with_metadata`), plus dlt's own `_dlt_load_id`/`_dlt_id`. These describe the *load*, not the *data* — they
  say nothing about what a row means, only when and how it arrived.
- **Deduplicate at the transport level.** `primary_key` on several `append` resources (`ingestion/relational.py`)
  lets dlt's incremental extraction skip re-sending a row it already delivered at a previous run's cursor
  boundary. This is idempotency, not data cleaning — it prevents the same row from being sent twice by the
  *pipeline*, and is explicitly documented (`ingestion/README.md`) as **not** collapsing genuine duplicate
  rows the source itself produced (`orders`' injected duplicate-`order_id` defect lands in `raw` twice,
  faithfully, on the first load, exactly as the source sent it).

**Ingestion is forbidden from:**
- Converting currency or normalizing units (`payments`/`refunds` land in raw exactly as the source's
  cents-vs-decimal defect produced them; `AE-07`'s `cents_to_decimal()` macro is where that gets fixed).
- Filtering rows for any reason — no "drop test accounts," no "skip cancelled orders." A row that entered
  the source enters `raw`.
- Renaming columns to friendlier names, or restructuring the shape of a nested field for readability
  (`web_events.geo` stays a JSON blob in raw; unpacking `geo.country` into its own column, if it's ever
  worth doing, is staging's decision to make and re-make).
- Resolving business meaning from ambiguous data — the `naive_utc_timestamps` example above is the concrete
  case; more generally, anything that requires *interpreting* what a value represents, rather than just
  preserving it, belongs downstream.

## Audit

`ingestion/relational.py`, `ingestion/web_events.py`, and `ingestion/common.py` were re-read end to end
against this list before writing this ADR (rather than assumed clean going in). No violation was found;
`grep -rni "currency\|rename\|filter"` across `ingestion/*.py` returns no matches — every hit is in this
project's own docs describing the policy, not in code. `support_tickets`' stray trailing comma (a hand-maintained
CSV export defect) is tolerated *structurally* in `ingestion/relational.py` — the row isn't dropped — but
the messy `status` casing itself is explicitly left untouched, with a comment pointing at `AE-15` to
normalize it later; that comment predates this ADR and turned out to already be drawing the line correctly.

## The one legitimate exception class: PII redaction

Real pipelines sometimes need to enforce that certain values *never* land in a raw table at all — a payment
card number, a national ID, health data under a regulatory regime that forbids storing it even
transiently. That's the one case where "no business logic in ingestion" gets relaxed: the decision to
redact isn't optional or revisable at query time, and re-deriving it from an already-contaminated raw table
doesn't help, because the point is that the value should never have been persisted in the first place.

**This project doesn't have that case today.** The Halcyon generator (`AE-02`) doesn't emit anything in
that category — `customers.email` is the closest candidate, and it's treated as an ordinary business
attribute rather than regulated PII in this domain, consistent with `consent_flag` being modeled as a
business signal rather than a legal gate. If a future entity introduced something in that category (a card
number, a government ID), the correct fix would be redaction *in the source*, before the generator ever
writes it to `data/raw/`, or a documented field-level drop inside the ingestion resource with an explicit
comment citing this ADR — not silence.

## What this costs

Every transformation deferred to staging means writing it in SQL/Jinja instead of Python, and re-deriving
it on every `dbt build` rather than paying the cost once at ingestion time. For a warehouse this size, that
cost is negligible; the payoff is that `raw` can always be trusted as the literal record of what the source
sent, so every downstream bug can be root-caused by asking "was this wrong in the source, or wrong in a
transformation" — a question that's unanswerable once ingestion has already started making judgment calls.
