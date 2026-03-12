"""
Economic Calendar Collector
Uses Trading Economics calendar API to fetch macro releases.
"""
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional, List

import pytz
import requests
from dateutil import parser


from src.config.settings import (
    TRADING_ECONOMICS_API_KEY,
    TIMEZONE,
    US_EASTERN_TZ,
    ECONOMIC_CALENDAR_COUNTRIES,
    ECONOMIC_CALENDAR_IMPORTANCE_MIN,
)


@dataclass
class EconomicEvent:
    """Represents a single economic calendar event."""
    event: str
    country: str
    date_et: datetime
    importance: Optional[int] = None
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    unit: Optional[str] = None
    currency: Optional[str] = None

    def to_report_row(self, tz_taipei) -> dict:
        dt_tw = self.date_et.astimezone(tz_taipei)
        return {
            "time_et": self.date_et.strftime("%H:%M"),
            "time_taipei": dt_tw.strftime("%H:%M"),
            "country": self.country,
            "event": self.event,
            "importance": self.importance,
            "forecast": self.forecast,
            "previous": self.previous,
        }


class EconomicCalendarCollector:
    """Fetches economic calendar events from Trading Economics."""

    BASE_URL = "https://api.tradingeconomics.com/calendar"

    def __init__(self):
        self.api_key = TRADING_ECONOMICS_API_KEY
        self.tz_et = pytz.timezone(US_EASTERN_TZ)
        self.tz_taipei = pytz.timezone(TIMEZONE)
        self.last_warning = ""

    def get_events_for_date(
        self,
        date_et: date,
        countries: Optional[list] = None,
        importance_min: Optional[int] = None,
    ) -> List[EconomicEvent]:
        self.last_warning = ""

        if not self.api_key:
            self.last_warning = "未設定 TRADING_ECONOMICS_API_KEY"
            return []

        start = date_et.strftime("%Y-%m-%d")
        url = f"{self.BASE_URL}/country/All/{start}/{start}"
        params = {"c": self.api_key}

        try:
            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            self.last_warning = f"Trading Economics API error: {e}"
            return []

        countries = countries if countries is not None else ECONOMIC_CALENDAR_COUNTRIES
        importance_min = (
            importance_min if importance_min is not None else ECONOMIC_CALENDAR_IMPORTANCE_MIN
        )

        events: list[EconomicEvent] = []
        for item in data if isinstance(data, list) else []:
            country = (item.get("Country") or "").strip()
            if countries and country and country not in countries:
                continue

            importance_val = None
            if item.get("Importance") is not None:
                try:
                    importance_val = int(item.get("Importance"))
                except Exception:
                    importance_val = None

            if importance_val is not None and importance_min and importance_val < importance_min:
                continue

            dt = self._parse_date(item.get("Date"))
            if not dt:
                continue

            event = (item.get("Event") or item.get("Indicator") or "Unknown").strip()
            if not event:
                continue

            events.append(
                EconomicEvent(
                    event=event,
                    country=country or "Unknown",
                    date_et=dt,
                    importance=importance_val,
                    actual=_safe_str(item.get("Actual")),
                    forecast=_safe_str(item.get("Forecast") or item.get("TEForecast")),
                    previous=_safe_str(item.get("Previous")),
                    unit=_safe_str(item.get("Unit")),
                    currency=_safe_str(item.get("Currency")),
                )
            )

        events.sort(key=lambda e: e.date_et)
        return events

    def to_report_rows(self, events: list[EconomicEvent]) -> list[dict]:
        return [e.to_report_row(self.tz_taipei) for e in events]

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            dt = parser.isoparse(date_str)
        except Exception:
            try:
                dt = parser.parse(date_str)
            except Exception:
                return None
        if dt.tzinfo is None:
            dt = self.tz_et.localize(dt)
        else:
            dt = dt.astimezone(self.tz_et)
        return dt


def _safe_str(value) -> str:
    if value is None:
        return ""
    return str(value)
