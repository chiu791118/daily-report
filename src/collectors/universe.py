"""
Universe Collector
Builds a ticker universe from FMP constituents and ETF holdings.
"""
from dataclasses import dataclass
from typing import Optional
import re

import requests


from src.config.settings import (
    FMP_API_KEY,
    UNIVERSE_INCLUDE_SP500,
    UNIVERSE_ETF_HOLDINGS,
)


@dataclass
class UniverseData:
    """Universe tickers and name mappings."""
    tickers: set
    ticker_to_name: dict
    name_to_ticker: dict


class UniverseCollector:
    """Fetches index constituents and ETF holdings to build a universe."""

    BASE_URL = "https://financialmodelingprep.com/stable"

    def __init__(self):
        self.api_key = FMP_API_KEY
        self.last_warning = ""

    def get_universe(self) -> UniverseData:
        self.last_warning = ""

        if not self.api_key:
            self.last_warning = "未設定 FMP_API_KEY"
            return UniverseData(set(), {}, {})

        tickers: dict[str, str] = {}

        if UNIVERSE_INCLUDE_SP500:
            for item in self._fetch_sp500():
                symbol = (item.get("symbol") or "").strip().upper()
                name = (item.get("name") or "").strip()
                if symbol:
                    tickers.setdefault(symbol, name)

        for etf in UNIVERSE_ETF_HOLDINGS:
            for item in self._fetch_etf_holdings(etf):
                symbol = (item.get("symbol") or item.get("asset") or "").strip().upper()
                name = (item.get("name") or item.get("assetName") or "").strip()
                if symbol:
                    tickers.setdefault(symbol, name)

        ticker_to_name = {k: v for k, v in tickers.items()}
        name_to_ticker: dict[str, str] = {}
        for symbol, name in ticker_to_name.items():
            if not name:
                continue
            raw_name = name.lower().strip()
            if len(raw_name) >= 4:
                name_to_ticker.setdefault(raw_name, symbol)
            normalized = _normalize_name(name)
            if normalized and len(normalized) >= 4:
                name_to_ticker.setdefault(normalized, symbol)

        return UniverseData(set(ticker_to_name.keys()), ticker_to_name, name_to_ticker)

    def _fetch_sp500(self) -> list:
        url = f"{self.BASE_URL}/sp500-constituent"
        params = {"apikey": self.api_key}
        return _safe_fetch(url, params)

    def _fetch_etf_holdings(self, symbol: str) -> list:
        url = f"{self.BASE_URL}/etf/holdings"
        params = {"symbol": symbol, "apikey": self.api_key}
        return _safe_fetch(url, params)


def _safe_fetch(url: str, params: dict) -> list:
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def _normalize_name(name: str) -> str:
    text = name.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    suffixes = [
        "inc", "incorporated", "corp", "corporation", "ltd", "plc", "co",
        "company", "holdings", "holding", "group", "sa", "ag", "nv", "lp",
    ]
    for suffix in suffixes:
        text = re.sub(rf"\b{suffix}\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
