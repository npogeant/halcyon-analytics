from __future__ import annotations

from datetime import date, timedelta


def month_ends(start: date, end: date) -> list[date]:
    """Last calendar day of every month from start's month through end's month."""
    ends = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        next_month = date(year + (month == 12), month % 12 + 1, 1)
        month_end = next_month - timedelta(days=1)
        ends.append(min(month_end, end))
        year, month = next_month.year, next_month.month
    return ends


def day_range(start: date, end: date) -> list[date]:
    n = (end - start).days
    return [start + timedelta(days=i) for i in range(n + 1)]
