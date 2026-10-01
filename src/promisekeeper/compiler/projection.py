from __future__ import annotations
import math
from datetime import date, timedelta

def add_business_days(start: date, days: float) -> date:
    """Mon-Fri only (no holiday calendar). Fractional days round up: a 4.5 day
    promise lands on the 5th business day."""
    remaining = max(0, math.ceil(days - 1e-9))
    d = start
    while remaining > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            remaining -= 1
    return d
