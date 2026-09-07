{% macro to_utc(column) %}
    {#
        Normalizes the naive-vs-UTC-suffixed timestamp defect (AE-02) into a single
        TIMESTAMPTZ. The business assumption made here -- and it is a business
        assumption, which is exactly why this lives in staging and not ingestion
        (docs/adr/0003-elt-boundary.md) -- is that a naive timestamp from this
        source already represents UTC, just missing the marker; it is not
        reinterpreted as any other timezone.

        Explicit `AT TIME ZONE 'UTC'` rather than a bare CAST: a bare
        `CAST(col AS TIMESTAMPTZ)` happens to produce the same result today because
        this session's TimeZone defaults to UTC, but that makes correctness depend
        on an ambient setting instead of being true regardless of it.
    #}
    (CAST(REPLACE({{ column }}, 'Z', '') AS TIMESTAMP) AT TIME ZONE 'UTC')
{% endmacro %}
