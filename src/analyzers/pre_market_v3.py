"""
Pre-Market V3 Analyzer
Generates a focused pre-market brief based on structured data.
"""
import json
import re
from typing import Optional

from google import genai
from google.genai import types

import pytz


from src.config.settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    TIMEZONE,
    US_EASTERN_TZ,
)
from src.prompts.pre_market import PRE_MARKET_V3_PROMPT, HIDDEN_LAYER_PROMPT
from src.collectors.universe import UniverseData


class PreMarketV3Analyzer:
    """Analyzer for generating Pre-market V3 report sections."""

    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not set in environment")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model = GEMINI_MODEL
        self.tz_taipei = pytz.timezone(TIMEZONE)
        self.tz_et = pytz.timezone(US_EASTERN_TZ)

    def _run_hidden_layer(
        self,
        yesterday_report: dict,
        news_items: list,
        sec_summary: str,
        fda_summary: str,
        market_overview,
    ) -> dict:
        """Run hidden processing layer: compare today vs yesterday to identify changes."""
        if yesterday_report and yesterday_report.get("available"):
            yesterday_text = yesterday_report["content"]
            if yesterday_report.get("fallback_note"):
                yesterday_text = f"[注意: {yesterday_report['fallback_note']}]\n\n{yesterday_text}"
        else:
            yesterday_text = "（昨日報告不可用）"

        news_text = "\n".join(
            f"- [{item.source}] {item.title}" for item in news_items[:30]
        ) or "無新聞數據"

        market_parts = []
        if market_overview.sp500:
            market_parts.append(
                f"S&P 500: {market_overview.sp500.current_price:,.2f} ({market_overview.sp500.change_percent:+.2f}%)"
            )
        if market_overview.nasdaq:
            market_parts.append(
                f"NASDAQ: {market_overview.nasdaq.current_price:,.2f} ({market_overview.nasdaq.change_percent:+.2f}%)"
            )
        if market_overview.vix is not None:
            market_parts.append(f"VIX: {market_overview.vix:.2f}")
        market_text = "\n".join(market_parts) or "無市場數據"

        prompt = HIDDEN_LAYER_PROMPT.format(
            yesterday_report=yesterday_text,
            news_data=news_text,
            sec_data=sec_summary or "無 SEC 數據",
            fda_data=fda_summary or "無 FDA 數據",
            market_data=market_text,
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=2000,
                ),
            )
            result = self._parse_json(response.text)
            if result:
                print(
                    f"   Hidden layer: {len(result.get('macro_changes', []))} macro, "
                    f"{len(result.get('company_changes', []))} company changes"
                )
            return result
        except Exception as e:
            print(f"   ⚠️ Hidden layer error: {e}")
            return {}

    def generate_sections(
        self,
        market_overview,
        economic_events: list,
        earnings_events: list,
        news_items: list,
        watchlist_stocks: list,
        universe_data: UniverseData,
        yesterday_report: dict = None,
        sec_summary: str = "",
        fda_summary: str = "",
    ) -> tuple[dict, dict]:
        """
        Returns:
            sections: dict of report sections
            meta: dict with symbols and news digest
        """
        # Run hidden layer first to get temporal change signals
        yesterday_changes = {}
        if yesterday_report is not None:
            print("   Running hidden layer analysis...")
            yesterday_changes = self._run_hidden_layer(
                yesterday_report=yesterday_report,
                news_items=news_items,
                sec_summary=sec_summary,
                fda_summary=fda_summary,
                market_overview=market_overview,
            )

        watchlist_candidates, watchlist_symbols = self._build_watchlist_candidates(
            watchlist_stocks, news_items, earnings_events
        )
        event_candidates, event_symbols = self._build_event_driven_candidates(
            news_items, universe_data, watchlist_symbols
        )
        news_digest = self._build_news_digest(news_items)

        data_pack = {
            "market_overview": self._format_market_overview(market_overview),
            "economic_events": [
                {
                    "time_et": e.to_report_row(self.tz_taipei)["time_et"],
                    "time_taipei": e.to_report_row(self.tz_taipei)["time_taipei"],
                    "country": e.country,
                    "event": e.event,
                    "importance": e.importance,
                    "forecast": e.forecast,
                    "previous": e.previous,
                }
                for e in economic_events[:12]
            ],
            "earnings_events": [
                {
                    "symbol": e.symbol,
                    "company": e.company,
                    "time_et": e.time_et,
                    "time_taipei": e.time_taipei,
                    "eps_estimate": e.eps_estimate,
                    "revenue_estimate": e.revenue_estimate,
                }
                for e in earnings_events[:20]
            ],
            "news_highlights": news_digest[:20],
            "watchlist_candidates": watchlist_candidates[:15],
            "event_driven_candidates": event_candidates[:15],
            "yesterday_changes": yesterday_changes,
        }

        prompt = PRE_MARKET_V3_PROMPT.format(
            data_pack=json.dumps(data_pack, ensure_ascii=False, indent=2)
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=2500,
            ),
        )

        sections = self._parse_json(response.text)

        if not sections:
            sections = self._fallback_sections(watchlist_candidates, event_candidates)

        meta = {
            "watchlist_focus_symbols": [c["symbol"] for c in watchlist_candidates[:8]],
            "event_driven_symbols": [c["symbol"] for c in event_candidates[:8]],
            "news_digest": news_digest[:12],
            "yesterday_changes": yesterday_changes,
        }

        return sections, meta

    def _build_watchlist_candidates(self, stocks, news_items, earnings_events):
        earnings_symbols = {e.symbol for e in earnings_events}
        news_symbols = set()
        for item in news_items:
            for t in item.related_tickers or []:
                news_symbols.add(t)

        candidates = []
        for stock in stocks:
            reasons = []
            score = 0

            if stock.symbol in earnings_symbols:
                reasons.append("今日財報")
                score += 3
            if stock.symbol in news_symbols:
                reasons.append("今日新聞提及")
                score += 2
            if abs(stock.change_percent) >= 2:
                reasons.append(f"單日波動 {stock.change_percent:+.2f}%")
                score += 1
            if stock.change_1w and abs(stock.change_1w) >= 5:
                reasons.append(f"近一週 {stock.change_1w:+.2f}%")
                score += 1
            if stock.rsi_14:
                if stock.rsi_14 >= 70:
                    reasons.append(f"RSI {stock.rsi_14:.0f} 超買")
                    score += 1
                elif stock.rsi_14 <= 30:
                    reasons.append(f"RSI {stock.rsi_14:.0f} 超賣")
                    score += 1
            if stock.volume_ratio and stock.volume_ratio >= 1.5:
                reasons.append(f"成交量放大 {stock.volume_ratio:.2f}x")
                score += 1

            if stock.support_levels:
                if _near_level(stock.current_price, stock.support_levels):
                    reasons.append("接近支撐位")
                    score += 1
            if stock.resistance_levels:
                if _near_level(stock.current_price, stock.resistance_levels):
                    reasons.append("接近壓力位")
                    score += 1

            if not reasons:
                continue

            candidates.append(
                {
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "price": round(stock.current_price, 2),
                    "change_percent": round(stock.change_percent, 2),
                    "change_1w": round(stock.change_1w, 2) if stock.change_1w else "",
                    "change_1m": round(stock.change_1m, 2) if stock.change_1m else "",
                    "rsi": round(stock.rsi_14, 0) if stock.rsi_14 else "",
                    "trend": stock.trend,
                    "reasons": reasons,
                    "score": score,
                }
            )

        candidates.sort(key=lambda x: (x["score"], abs(x.get("change_percent", 0))), reverse=True)
        symbols = {c["symbol"] for c in candidates}
        return candidates, symbols

    def _build_event_driven_candidates(self, news_items, universe_data: UniverseData, watchlist_symbols: set):
        if not universe_data or not universe_data.tickers:
            return [], []

        candidates = {}
        for item in news_items:
            text = f"{item.title} {item.summary}".lower()

            matched = set()
            matched.update(_extract_ticker_tokens(item.title, universe_data.tickers))

            normalized_text = _normalize_text(text)
            for name, ticker in universe_data.name_to_ticker.items():
                if name and name in normalized_text:
                    matched.add(ticker)

            for ticker in matched:
                if ticker in watchlist_symbols:
                    continue
                if ticker not in universe_data.tickers:
                    continue

                entry = candidates.setdefault(
                    ticker,
                    {
                        "symbol": ticker,
                        "name": universe_data.ticker_to_name.get(ticker, ""),
                        "headlines": [],
                        "count": 0,
                    },
                )
                entry["count"] += 1
                if len(entry["headlines"]) < 3:
                    entry["headlines"].append(item.title)

        items = list(candidates.values())
        items.sort(key=lambda x: x["count"], reverse=True)
        symbols = [i["symbol"] for i in items]
        flattened = [
            {
                "symbol": i["symbol"],
                "name": i["name"],
                "headlines": i["headlines"],
                "count": i["count"],
            }
            for i in items
        ]
        return flattened, symbols

    def _build_news_digest(self, news_items: list) -> list[dict]:
        digest = []
        for item in news_items[:20]:
            try:
                dt_et = item.published.astimezone(self.tz_et)
                dt_tw = item.published.astimezone(self.tz_taipei)
                digest.append(
                    {
                        "source": item.source,
                        "title": item.title,
                        "time_et": dt_et.strftime("%H:%M"),
                        "time_taipei": dt_tw.strftime("%H:%M"),
                    }
                )
            except Exception:
                digest.append(
                    {
                        "source": item.source,
                        "title": item.title,
                        "time_et": "",
                        "time_taipei": "",
                    }
                )
        return digest

    def _format_market_overview(self, overview) -> dict:
        data = {}
        if overview.sp500:
            data["sp500"] = {
                "price": round(overview.sp500.current_price, 2),
                "change_percent": round(overview.sp500.change_percent, 2),
            }
        if overview.nasdaq:
            data["nasdaq"] = {
                "price": round(overview.nasdaq.current_price, 2),
                "change_percent": round(overview.nasdaq.change_percent, 2),
            }
        if overview.dow:
            data["dow"] = {
                "price": round(overview.dow.current_price, 2),
                "change_percent": round(overview.dow.change_percent, 2),
            }
        if overview.vix is not None:
            data["vix"] = {
                "value": round(overview.vix, 2),
                "change_percent": round(overview.vix_change or 0, 2),
            }
        data["sentiment"] = overview.market_sentiment
        return data

    def _parse_json(self, text: str) -> dict:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {}
        try:
            return json.loads(match.group())
        except Exception:
            return {}

    def _fallback_sections(self, watchlist_candidates, event_candidates):
        return {
            "executive_summary": [
                "LLM 解析失敗 → 請檢查模型輸出 → 以下為自動回退內容",
                "資料已收集完成 → 但結構化分析未能產出 → 請參考原始數據判斷",
                "建議手動檢視參考資料區段 → 確認數據源正常 → 下次執行應恢復",
            ],
            "watchlist_focus": [
                {
                    "symbol": c["symbol"],
                    "why": " / ".join(c.get("reasons", [])),
                    "watch": "留意開盤反應",
                }
                for c in watchlist_candidates[:5]
            ],
            "event_driven": [
                {
                    "symbol": c["symbol"],
                    "why": "；".join(c.get("headlines", [])[:2]),
                    "impact": "關注事件影響",
                }
                for c in event_candidates[:5]
            ],
        }


def _near_level(price: float, levels: list, threshold: float = 0.02) -> bool:
    if not price or not levels:
        return False
    for level in levels:
        try:
            lvl = float(level)
        except Exception:
            continue
        if lvl and abs(price - lvl) / lvl <= threshold:
            return True
    return False


def _extract_ticker_tokens(text: str, universe: set) -> set:
    tickers = set()
    if not text:
        return tickers
    for token in re.findall(r"\b[A-Z]{1,5}\b", text):
        if token in universe:
            tickers.add(token)
    return tickers


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
