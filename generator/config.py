from __future__ import annotations

from datetime import date

SEED = 20260831

N_CUSTOMERS = 5_000
N_PRODUCTS = 60

# Fixed history window (not "today") so the same seed is byte-identical on any run date.
START_DATE = date(2024, 9, 1)
END_DATE = date(2026, 8, 31)

# Fixed dates for the defects that need to land on a specific day.
SCHEMA_CHANGE_DATE = date(2025, 9, 1)
REFUND_SPIKE_DATE = date(2026, 3, 16)
WEB_EVENTS_SCHEMA_CHANGE_DATE = date(2025, 11, 1)

OUTPUT_DIR = "data/raw"

COUNTRIES = ["US", "GB", "FR", "DE", "CA", "AU", "NL", "ES"]
MARKETING_SEGMENTS = ["prospect", "trial", "active", "churned", "vip"]
PLAN_TIERS = ["free", "starter", "growth", "enterprise"]

# The conformed `channel` dimension (docs/adr/0002-conformed-dimensions.md). Every
# entity that carries a channel attribute draws from this same list, so CAC
# (marketing_spend) and attribution (customers, web_events) never drift apart.
CHANNELS = ["paid_search", "paid_social", "email", "affiliate", "display", "organic"]
DEVICES = ["desktop", "mobile", "tablet"]
DEVICE_WEIGHTS = [0.50, 0.40, 0.10]

# Marketing added campaign attribution to the event tracker partway through
# history (AE-05's schema-evolution defect) -- events before
# WEB_EVENTS_SCHEMA_CHANGE_DATE simply have no `utm_campaign` key at all.
CAMPAIGNS = ["spring_sale", "black_friday", "always_on", "referral_promo"]

# Every injected defect, on by default. See generator/README.md for what each one does
# and which backlog issue exercises it.
DEFECTS = {
    "duplicate_orders": True,
    "null_customer_id": True,
    "cents_vs_decimal": True,
    "naive_utc_timestamps": True,
    "late_web_events": True,
    "schema_change": True,
    "volume_anomaly": True,
    "web_events_schema_change": True,
}
