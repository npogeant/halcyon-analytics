from __future__ import annotations

from .. import config
from ..dates import day_range
from ..rng import rng_for
from ..writer import write_text_lines

CHANNELS = {
    "paid_search": (400, 1200),
    "paid_social": (300, 900),
    "email": (20, 80),
    "affiliate": (100, 400),
    "display": (150, 500),
    "organic": (0, 0),
}


def generate(defects: dict) -> dict:
    rng = rng_for(config.SEED, "marketing_spend")

    lines = []
    for day in day_range(config.START_DATE, config.END_DATE):
        for channel, (low, high) in CHANNELS.items():
            spend = 0.0 if high == 0 else round(float(rng.uniform(low, high)), 2)
            lines.append(f"{day.isoformat()},{channel},{spend},USD")

    write_text_lines(
        lines,
        f"{config.OUTPUT_DIR}/marketing_spend/marketing_spend.csv",
        header="date,channel,spend,currency",
    )

    return {"marketing_spend_rows": len(lines)}
