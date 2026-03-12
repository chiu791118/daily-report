"""Trading day utilities."""
from datetime import datetime, timedelta


def get_previous_trading_day(date: datetime, offset: int = 1) -> datetime:
    """Get the Nth previous trading day, skipping weekends.

    Args:
        date: Starting date.
        offset: How many trading days back (default 1 = most recent prior day).

    Note: Does not account for US market holidays, only weekends.
    """
    result = date
    days_back = 0
    while days_back < offset:
        result = result - timedelta(days=1)
        if result.weekday() < 5:  # 0=Mon … 4=Fri
            days_back += 1
    return result
