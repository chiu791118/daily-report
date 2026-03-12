"""
Earnings Calendar Collector
Uses Financial Modeling Prep earnings calendar.
"""
from dataclasses import dataclass
from datetime import datetime, date, time
from typing import Optional, List
import re

import pytz
import requests
from dateutil import parser


from src.config.settings import (
    FMP_API_KEY,
    TIMEZONE,
    US_EASTERN_TZ,
)


@dataclass
class EarningsEvent:
    """Represents a single earnings calendar event."""
    symbol: str
    company: str
    date_et: datetime
    time_et: str
    time_taipei: str
    eps_estimate: Optional[str] = None
    revenue_estimate: Optional[str] = None

    def to_report_row(self) -> dict:
        return {
            "symbol": self.symbol,
            "company": self.company,
            "time_et": self.time_et,
            "time_taipei": self.time_taipei,
            "eps_estimate": self.eps_estimate,
            "revenue_estimate": self.revenue_estimate,
        }


class EarningsCalendarCollector:
    """Fetches earnings calendar events from FMP."""

    BASE_URL = "https://financialmodelingprep.com/stable/earnings-calendar"

    def __init__(self):
        self.api_key = FMP_API_KEY
        self.tz_et = pytz.timezone(US_EASTERN_TZ)
        self.tz_taipei = pytz.timezone(TIMEZONE)
        self.last_warning = ""

    def get_events_for_date(self, date_et: date) -> List[EarningsEvent]:
        self.last_warning = ""

        if not self.api_key:
            self.last_warning = "未設定 FMP_API_KEY"
            return []

        date_str = date_et.strftime("%Y-%m-%d")
        params = {
            "from": date_str,
            "to": date_str,
            "apikey": self.api_key,
        }

        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            self.last_warning = f"FMP earnings calendar error: {e}"
            return []

        events: list[EarningsEvent] = []
        for item in data if isinstance(data, list) else []:
            symbol = (item.get("symbol") or "").strip().upper()
            if not symbol:
                continue

            company = (
                item.get("company")
                or item.get("companyName")
                or item.get("name")
                or ""
            )

            time_raw = str(item.get("time") or "").strip()
            dt_et, time_label = self._parse_time(date_et, time_raw)

            if not dt_et:
                dt_et = self.tz_et.localize(datetime.combine(date_et, time(0, 0)))

            dt_tw = dt_et.astimezone(self.tz_taipei)
            time_et, time_tw = self._format_time_labels(time_label, dt_et, dt_tw)

            eps_est = _safe_str(
                item.get("epsEstimated")
                or item.get("epsEstimate")
                or item.get("eps")
            )
            rev_est = _safe_str(
                item.get("revenueEstimated")
                or item.get("revenueEstimate")
                or item.get("revenue")
            )

            events.append(
                EarningsEvent(
                    symbol=symbol,
                    company=company,
                    date_et=dt_et,
                    time_et=time_et,
                    time_taipei=time_tw,
                    eps_estimate=eps_est,
                    revenue_estimate=rev_est,
                )
            )

        events.sort(key=lambda e: e.date_et)
        return events

    def to_report_rows(self, events: list[EarningsEvent]) -> list[dict]:
        return [e.to_report_row() for e in events]

    def _parse_time(self, date_et: date, time_raw: str):
        if not time_raw:
            return None, "TBD"

        t = time_raw.strip().lower()
        session_map = {
            "bmo": ("BMO", time(8, 0)),
            "before market open": ("BMO", time(8, 0)),
            "amc": ("AMC", time(16, 5)),
            "after market close": ("AMC", time(16, 5)),
            "dmt": ("DMT", time(12, 0)),
            "during market": ("DMT", time(12, 0)),
        }
        if t in session_map:
            label, tm = session_map[t]
            dt_et = self.tz_et.localize(datetime.combine(date_et, tm))
            return dt_et, label

        if re.match(r"^\d{1,2}:\d{2}$", t):
            try:
                tm = parser.parse(t).time()
                dt_et = self.tz_et.localize(datetime.combine(date_et, tm))
                return dt_et, ""
            except Exception:
                return None, time_raw.upper()

        return None, time_raw.upper()

    def _format_time_labels(self, label: str, dt_et: datetime, dt_tw: datetime):
        if label in {"BMO", "AMC", "DMT"}:
            return (
                f"{label} (~{dt_et.strftime('%H:%M')})",
                f"{label} (~{dt_tw.strftime('%H:%M')})",
            )

        if label and label != "TBD":
            return label, label

        return dt_et.strftime("%H:%M"), dt_tw.strftime("%H:%M")


def _safe_str(value) -> str:
    if value is None:
        return ""
    return str(value)
