"""
Pre-Market V4 Analyzer
4-stage LLM pipeline: Hidden Layer → News Analysis → Core Briefing → Portfolio & Discovery
Style: A (consulting brief) + D (systematic framework)
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
from src.prompts.pre_market.v4 import (
    HIDDEN_LAYER_PROMPT,
    NEWS_ANALYSIS_PROMPT,
    CORE_BRIEFING_PROMPT,
    PORTFOLIO_DISCOVERY_PROMPT,
)
from src.collectors.universe import UniverseData


class PreMarketV4Analyzer:
    """Analyzer for generating Pre-market V4 report sections via 4-stage LLM pipeline."""

    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not set in environment")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model = GEMINI_MODEL
        self.tz_taipei = pytz.timezone(TIMEZONE)
        self.tz_et = pytz.timezone(US_EASTERN_TZ)

    # ------------------------------------------------------------------
    # Stage 1: Hidden Layer
    # ------------------------------------------------------------------
    def _run_hidden_layer(
        self,
        yesterday_report: dict,
        news_items: list,
        sec_summary: str,
        fda_summary: str,
        market_overview,
    ) -> dict:
        """Compare today vs yesterday to identify changes."""
        if yesterday_report and yesterday_report.get("available"):
            yesterday_text = yesterday_report["content"]
            if yesterday_report.get("fallback_note"):
                yesterday_text = f"[注意: {yesterday_report['fallback_note']}]\n\n{yesterday_text}"
        else:
            yesterday_text = "（昨日報告不可用）"

        news_text = "\n".join(
            f"- [{item.source}] {item.title}" for item in news_items[:30]
        ) or "無新聞數據"

        market_text = self._format_market_text(market_overview)

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

    # ------------------------------------------------------------------
    # Stage 2: News Deep Dive
    # ------------------------------------------------------------------
    def _run_news_analysis(
        self,
        news_items: list,
        market_overview,
        sec_summary: str,
        fda_summary: str,
    ) -> dict:
        """Categorize and analyze news with 'so what' for each item."""
        news_text = "\n".join(
            f"- [{item.source}] {item.title}"
            + (f" — {item.summary[:120]}" if item.summary else "")
            for item in news_items[:35]
        ) or "無新聞數據"

        market_text = self._format_market_text(market_overview)

        prompt = NEWS_ANALYSIS_PROMPT.format(
            news_data=news_text,
            market_data=market_text,
            sec_data=sec_summary or "無 SEC 數據",
            fda_data=fda_summary or "無 FDA 數據",
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=3000,
                ),
            )
            result = self._parse_json(response.text)
            if result:
                counts = {k: len(v) for k, v in result.items() if isinstance(v, list)}
                print(f"   News analysis: {counts}")
            return result
        except Exception as e:
            print(f"   ⚠️ News analysis error: {e}")
            return {}

    # ------------------------------------------------------------------
    # Stage 3: Core Briefing
    # ------------------------------------------------------------------
    def _run_core_briefing(
        self,
        market_overview,
        yesterday_changes: dict,
        news_analysis: dict,
        economic_events: list,
        earnings_events: list,
        fda_summary: str,
        sec_summary: str,
    ) -> dict:
        """Generate executive summary, macro assessment, FDA highlights, allocation signals."""
        market_text = self._format_market_text(market_overview)

        econ_text = "\n".join(
            f"- {e.event} ({e.country}, 重要性{e.importance}) 預期:{e.forecast or '—'} 前值:{e.previous or '—'}"
            for e in economic_events[:12]
        ) or "今日無重大經濟數據"

        earnings_text = "\n".join(
            f"- {e.symbol} ({e.company}) EPS預期:{e.eps_estimate or '—'} 營收預期:{e.revenue_estimate or '—'}"
            for e in earnings_events[:15]
        ) or "今日無重大財報"

        prompt = CORE_BRIEFING_PROMPT.format(
            market_data=market_text,
            yesterday_changes=json.dumps(yesterday_changes, ensure_ascii=False, indent=2) if yesterday_changes else "無昨日比較數據",
            news_analysis=json.dumps(news_analysis, ensure_ascii=False, indent=2) if news_analysis else "無新聞分析",
            economic_events=econ_text,
            earnings_events=earnings_text,
            fda_data=fda_summary or "無 FDA 數據",
            sec_data=sec_summary or "無 SEC 數據",
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=3500,
                ),
            )
            result = self._parse_json(response.text)
            if result:
                es_count = len(result.get("executive_summary", []))
                alloc_count = len(result.get("allocation_signals", []))
                fda_count = len(result.get("fda_highlights", []))
                print(f"   Core briefing: {es_count} ES, {alloc_count} allocation, {fda_count} FDA")
            return result
        except Exception as e:
            print(f"   ⚠️ Core briefing error: {e}")
            return {}

    # ------------------------------------------------------------------
    # Stage 4: Portfolio & Discovery
    # ------------------------------------------------------------------
    def _run_portfolio_discovery(
        self,
        core_briefing: dict,
        news_analysis: dict,
        watchlist_candidates: list,
        event_candidates: list,
        yesterday_changes: dict,
    ) -> dict:
        """Analyze watchlist stocks and discover new themes/tickers."""
        es_text = "\n".join(
            f"{i+1}. {item}"
            for i, item in enumerate(core_briefing.get("executive_summary", []))
        ) or "無 ES"

        alloc_text = json.dumps(
            core_briefing.get("allocation_signals", []),
            ensure_ascii=False, indent=2,
        )

        watchlist_text = json.dumps(watchlist_candidates[:15], ensure_ascii=False, indent=2)
        event_text = json.dumps(event_candidates[:15], ensure_ascii=False, indent=2)

        prompt = PORTFOLIO_DISCOVERY_PROMPT.format(
            executive_summary=es_text,
            allocation_signals=alloc_text,
            news_analysis=json.dumps(news_analysis, ensure_ascii=False, indent=2) if news_analysis else "無",
            watchlist_data=watchlist_text,
            event_candidates=event_text,
            yesterday_changes=json.dumps(yesterday_changes, ensure_ascii=False, indent=2) if yesterday_changes else "無",
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=3500,
                ),
            )
            result = self._parse_json(response.text)
            if result:
                wl_count = len(result.get("watchlist_analysis", []))
                theme_count = len(result.get("theme_radar", []))
                anom_count = len(result.get("anomaly_tickers", []))
                print(f"   Portfolio: {wl_count} watchlist, {theme_count} themes, {anom_count} anomalies")
            return result
        except Exception as e:
            print(f"   ⚠️ Portfolio discovery error: {e}")
            return {}

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
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
        Run the 4-stage pipeline and return all sections.

        Returns:
            sections: dict with all report sections
            meta: dict with auxiliary data (symbols, news digest)
        """
        # --- Stage 1: Hidden Layer ---
        print("   [1/4] Hidden layer analysis...")
        yesterday_changes = {}
        if yesterday_report is not None:
            yesterday_changes = self._run_hidden_layer(
                yesterday_report=yesterday_report,
                news_items=news_items,
                sec_summary=sec_summary,
                fda_summary=fda_summary,
                market_overview=market_overview,
            )

        # --- Stage 2: News Deep Dive ---
        print("   [2/4] News analysis...")
        news_analysis = self._run_news_analysis(
            news_items=news_items,
            market_overview=market_overview,
            sec_summary=sec_summary,
            fda_summary=fda_summary,
        )

        # --- Stage 3: Core Briefing ---
        print("   [3/4] Core briefing...")
        core_briefing = self._run_core_briefing(
            market_overview=market_overview,
            yesterday_changes=yesterday_changes,
            news_analysis=news_analysis,
            economic_events=economic_events,
            earnings_events=earnings_events,
            fda_summary=fda_summary,
            sec_summary=sec_summary,
        )

        # --- Build watchlist / event candidates for Stage 4 ---
        watchlist_candidates, watchlist_symbols = self._build_watchlist_candidates(
            watchlist_stocks, news_items, earnings_events
        )
        event_candidates, _ = self._build_event_driven_candidates(
            news_items, universe_data, watchlist_symbols
        )

        # --- Stage 4: Portfolio & Discovery ---
        print("   [4/4] Portfolio & discovery...")
        portfolio = self._run_portfolio_discovery(
            core_briefing=core_briefing,
            news_analysis=news_analysis,
            watchlist_candidates=watchlist_candidates,
            event_candidates=event_candidates,
            yesterday_changes=yesterday_changes,
        )

        # --- Assemble all sections ---
        sections = {
            "executive_summary": core_briefing.get("executive_summary", []),
            "macro_assessment": core_briefing.get("macro_assessment", {}),
            "fda_highlights": core_briefing.get("fda_highlights", []),
            "allocation_signals": core_briefing.get("allocation_signals", []),
            "news_analysis": news_analysis,
            "watchlist_analysis": portfolio.get("watchlist_analysis", []),
            "theme_radar": portfolio.get("theme_radar", []),
            "anomaly_tickers": portfolio.get("anomaly_tickers", []),
            "yesterday_changes": yesterday_changes,
        }

        # Build news digest for reference section
        news_digest = self._build_news_digest(news_items)

        meta = {
            "news_digest": news_digest[:12],
            "yesterday_changes": yesterday_changes,
            "watchlist_symbols": [c["symbol"] for c in watchlist_candidates[:8]],
            "event_symbols": [c["symbol"] for c in event_candidates[:8]],
        }

        return sections, meta

    # ------------------------------------------------------------------
    # Helpers (reused from V3)
    # ------------------------------------------------------------------
    def _format_market_text(self, market_overview) -> str:
        parts = []
        if market_overview.sp500:
            parts.append(
                f"S&P 500: {market_overview.sp500.current_price:,.2f} ({market_overview.sp500.change_percent:+.2f}%)"
            )
        if market_overview.nasdaq:
            parts.append(
                f"NASDAQ: {market_overview.nasdaq.current_price:,.2f} ({market_overview.nasdaq.change_percent:+.2f}%)"
            )
        if market_overview.dow:
            parts.append(
                f"Dow Jones: {market_overview.dow.current_price:,.2f} ({market_overview.dow.change_percent:+.2f}%)"
            )
        if market_overview.vix is not None:
            parts.append(f"VIX: {market_overview.vix:.2f}")
        if market_overview.market_sentiment:
            parts.append(f"市場情緒: {market_overview.market_sentiment}")
        return "\n".join(parts) or "無市場數據"

    def _build_watchlist_candidates(self, stocks, news_items, earnings_events):
        """Score and rank watchlist stocks by signal strength."""
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
            if stock.support_levels and _near_level(stock.current_price, stock.support_levels):
                reasons.append("接近支撐位")
                score += 1
            if stock.resistance_levels and _near_level(stock.current_price, stock.resistance_levels):
                reasons.append("接近壓力位")
                score += 1

            if not reasons:
                continue

            candidates.append({
                "symbol": stock.symbol,
                "name": stock.name,
                "price": round(stock.current_price, 2),
                "change_percent": round(stock.change_percent, 2),
                "change_1w": round(stock.change_1w, 2) if stock.change_1w else "",
                "change_1m": round(stock.change_1m, 2) if stock.change_1m else "",
                "rsi": round(stock.rsi_14, 0) if stock.rsi_14 else "",
                "trend": stock.trend,
                "volume_ratio": round(stock.volume_ratio, 2) if stock.volume_ratio else "",
                "reasons": reasons,
                "score": score,
            })

        candidates.sort(key=lambda x: (x["score"], abs(x.get("change_percent", 0))), reverse=True)
        symbols = {c["symbol"] for c in candidates}
        return candidates, symbols

    def _build_event_driven_candidates(self, news_items, universe_data: UniverseData, watchlist_symbols: set):
        """Find ticker mentions in news that are NOT in the watchlist."""
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

        items = sorted(candidates.values(), key=lambda x: x["count"], reverse=True)
        symbols = [i["symbol"] for i in items]
        return items, symbols

    def _build_news_digest(self, news_items: list) -> list[dict]:
        """Build a simple news digest for the reference section."""
        digest = []
        for item in news_items[:20]:
            try:
                dt_et = item.published.astimezone(self.tz_et)
                dt_tw = item.published.astimezone(self.tz_taipei)
                digest.append({
                    "source": item.source,
                    "title": item.title,
                    "time_et": dt_et.strftime("%H:%M"),
                    "time_taipei": dt_tw.strftime("%H:%M"),
                })
            except Exception:
                digest.append({
                    "source": item.source,
                    "title": item.title,
                    "time_et": "",
                    "time_taipei": "",
                })
        return digest

    def _parse_json(self, text: str) -> dict:
        """Extract JSON from LLM response text."""
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {}
        try:
            return json.loads(match.group())
        except Exception:
            return {}


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

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
