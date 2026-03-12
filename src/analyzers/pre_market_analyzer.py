"""
Pre-Market Analyzer Module

Implements the 6-layer pre-market report structure:
- Hidden Processing Layer (internal, not output)
- Layer 0: Executive Snapshot
- Layer 1: What Changed Today
- Layer 2: Structural Interpretation
- Layer 3: Asset Allocation Watchlist
- Layer 4: Equity Signals
- Layer 5: Decision Log
"""
import json
import re
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import types


from src.config.settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
)
from src.prompts.pre_market import (
    HIDDEN_LAYER_PROMPT,
    LAYER_0_1_PROMPT,
    LAYER_2_3_PROMPT,
    LAYER_4_5_PROMPT,
    NEWS_SUMMARY_PROMPT,
)


@dataclass
class LayeredReportResult:
    """Result of layered report generation."""
    layer_0: str  # Executive Snapshot
    layer_1: str  # What Changed Today
    layer_2: str  # Structural Interpretation
    layer_3: str  # Asset Allocation Watchlist
    layer_4: str  # Equity Signals
    layer_5: str  # Decision Log
    news_summary: str  # Paragraph-style news summary
    market_appendix: str  # Market data appendix
    hidden_layer_output: dict  # Internal processing result
    extracted_tickers: list  # Tickers from Layer 4


class PreMarketAnalyzer:
    """Analyzer for generating layered pre-market reports."""

    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not set in environment")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model = GEMINI_MODEL

    def process_hidden_layer(
        self,
        yesterday_report: dict,
        news_data: str,
        sec_data: str,
        fda_data: str,
        market_data: str,
    ) -> dict:
        """
        Process Hidden Layer - internal data processing, not output to report.

        Args:
            yesterday_report: Dict with 'content', 'available', 'source', 'fallback_note'
            news_data: Formatted news items
            sec_data: Formatted SEC filings
            fda_data: Formatted FDA updates
            market_data: Formatted market overview

        Returns:
            Dict with processed changes (macro, industry, company)
        """
        yesterday_content = yesterday_report.get("content", "")
        if not yesterday_report.get("available", False):
            yesterday_content = "【昨日報告不可用】\n" + yesterday_report.get("fallback_note", "")

        prompt = HIDDEN_LAYER_PROMPT.format(
            yesterday_report=yesterday_content[:8000] if yesterday_content else "無昨日報告",
            news_data=news_data[:6000],
            sec_data=sec_data[:2000] if sec_data else "無 SEC 公告",
            fda_data=fda_data[:2000] if fda_data else "無 FDA 動態",
            market_data=market_data,
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

            # Parse JSON from response
            text = response.text
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                result = json.loads(json_match.group())
                # Add yesterday availability info
                result["yesterday_unavailable"] = not yesterday_report.get("available", False)
                result["yesterday_note"] = yesterday_report.get("fallback_note", "")
                return result
            else:
                return {
                    "macro_changes": [],
                    "industry_changes": [],
                    "company_changes": [],
                    "filtered_noise": [],
                    "yesterday_unavailable": not yesterday_report.get("available", False),
                    "yesterday_note": yesterday_report.get("fallback_note", ""),
                    "error": "Failed to parse hidden layer output",
                }

        except Exception as e:
            return {
                "macro_changes": [],
                "industry_changes": [],
                "company_changes": [],
                "filtered_noise": [],
                "yesterday_unavailable": not yesterday_report.get("available", False),
                "yesterday_note": yesterday_report.get("fallback_note", ""),
                "error": str(e),
            }

    def _generate_layer_0_1(
        self,
        hidden_layer_output: dict,
        market_data: str,
        news_data: str,
    ) -> tuple[str, str]:
        """Generate Layer 0 (Executive Snapshot) and Layer 1 (What Changed Today)."""
        # Prepare yesterday warning if needed
        yesterday_warning = ""
        if hidden_layer_output.get("yesterday_unavailable", False):
            note = hidden_layer_output.get("yesterday_note", "昨日報告不可用")
            yesterday_warning = f"\n**注意**：在 Layer 0 的開頭加入以下警告：\n⚠️ {note}\n"

        prompt = LAYER_0_1_PROMPT.format(
            hidden_layer_output=json.dumps(hidden_layer_output, ensure_ascii=False, indent=2),
            market_data=market_data,
            news_data=news_data[:4000],
            yesterday_warning=yesterday_warning,
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=4000,
                ),
            )

            text = response.text

            # Split into Layer 0 and Layer 1
            layer_0 = ""
            layer_1 = ""

            # Find Layer 0 section
            layer_0_match = re.search(
                r'### Layer 0.*?(?=### Layer 1|$)',
                text,
                re.DOTALL | re.IGNORECASE
            )
            if layer_0_match:
                layer_0 = layer_0_match.group().strip()

            # Find Layer 1 section
            layer_1_match = re.search(
                r'### Layer 1.*',
                text,
                re.DOTALL | re.IGNORECASE
            )
            if layer_1_match:
                layer_1 = layer_1_match.group().strip()

            # If parsing failed, use full response
            if not layer_0 and not layer_1:
                parts = text.split("Layer 1", 1)
                if len(parts) == 2:
                    layer_0 = parts[0].strip()
                    layer_1 = "Layer 1" + parts[1].strip()
                else:
                    layer_0 = text
                    layer_1 = ""

            return layer_0, layer_1

        except Exception as e:
            return f"生成 Layer 0-1 時發生錯誤: {e}", ""

    def _generate_layer_2_3(
        self,
        layer_0_content: str,
        layer_1_content: str,
        market_data: str,
    ) -> tuple[str, str]:
        """Generate Layer 2 (Structural Interpretation) and Layer 3 (Asset Allocation)."""
        prompt = LAYER_2_3_PROMPT.format(
            layer_0_content=layer_0_content,
            layer_1_content=layer_1_content,
            market_data=market_data,
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=3000,
                ),
            )

            text = response.text

            # Split into Layer 2 and Layer 3
            layer_2 = ""
            layer_3 = ""

            # Find Layer 2 section
            layer_2_match = re.search(
                r'### Layer 2.*?(?=### Layer 3|$)',
                text,
                re.DOTALL | re.IGNORECASE
            )
            if layer_2_match:
                layer_2 = layer_2_match.group().strip()

            # Find Layer 3 section
            layer_3_match = re.search(
                r'### Layer 3.*',
                text,
                re.DOTALL | re.IGNORECASE
            )
            if layer_3_match:
                layer_3 = layer_3_match.group().strip()

            # If parsing failed, try alternative split
            if not layer_2 and not layer_3:
                parts = text.split("Layer 3", 1)
                if len(parts) == 2:
                    layer_2 = parts[0].strip()
                    layer_3 = "Layer 3" + parts[1].strip()
                else:
                    layer_2 = text
                    layer_3 = ""

            return layer_2, layer_3

        except Exception as e:
            return f"生成 Layer 2-3 時發生錯誤: {e}", ""

    def _generate_layer_4_5(
        self,
        layer_0_content: str,
        layer_1_content: str,
        layer_2_content: str,
        layer_3_content: str,
        watchlist_data: str,
        company_changes: list,
    ) -> tuple[str, str]:
        """Generate Layer 4 (Equity Signals) and Layer 5 (Decision Log)."""
        prompt = LAYER_4_5_PROMPT.format(
            layer_0_content=layer_0_content,
            layer_1_content=layer_1_content,
            layer_2_content=layer_2_content,
            layer_3_content=layer_3_content,
            watchlist_data=watchlist_data[:3000],
            company_changes=json.dumps(company_changes, ensure_ascii=False, indent=2) if company_changes else "無公司變化",
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=3000,
                ),
            )

            text = response.text

            # Split into Layer 4 and Layer 5
            layer_4 = ""
            layer_5 = ""

            # Find Layer 4 section
            layer_4_match = re.search(
                r'### Layer 4.*?(?=### Layer 5|$)',
                text,
                re.DOTALL | re.IGNORECASE
            )
            if layer_4_match:
                layer_4 = layer_4_match.group().strip()

            # Find Layer 5 section
            layer_5_match = re.search(
                r'### Layer 5.*',
                text,
                re.DOTALL | re.IGNORECASE
            )
            if layer_5_match:
                layer_5 = layer_5_match.group().strip()

            # If parsing failed, try alternative split
            if not layer_4 and not layer_5:
                parts = text.split("Layer 5", 1)
                if len(parts) == 2:
                    layer_4 = parts[0].strip()
                    layer_5 = "Layer 5" + parts[1].strip()
                else:
                    layer_4 = text
                    layer_5 = ""

            return layer_4, layer_5

        except Exception as e:
            return f"生成 Layer 4-5 時發生錯誤: {e}", ""

    def generate_news_summary(
        self,
        news_data: str,
        market_data: str,
    ) -> str:
        """Generate paragraph-style news summary."""
        prompt = NEWS_SUMMARY_PROMPT.format(
            news_data=news_data[:5000],
            market_data=market_data,
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=1000,
                ),
            )
            return response.text.strip()

        except Exception as e:
            return f"無法生成新聞摘要: {e}"

    def _format_market_appendix(self, market_overview) -> str:
        """Format market data as appendix table."""
        lines = ["## 📊 市場數據附錄\n"]

        # Index table
        lines.append("| 指數 | 收盤價 | 漲跌幅 |")
        lines.append("|------|--------|--------|")

        if market_overview.sp500:
            lines.append(
                f"| S&P 500 | {market_overview.sp500.current_price:,.2f} | "
                f"{market_overview.sp500.change_percent:+.2f}% |"
            )
        if market_overview.nasdaq:
            lines.append(
                f"| NASDAQ | {market_overview.nasdaq.current_price:,.2f} | "
                f"{market_overview.nasdaq.change_percent:+.2f}% |"
            )
        if market_overview.dow:
            lines.append(
                f"| Dow Jones | {market_overview.dow.current_price:,.2f} | "
                f"{market_overview.dow.change_percent:+.2f}% |"
            )
        if market_overview.vix:
            lines.append(
                f"| VIX | {market_overview.vix:.2f} | "
                f"{market_overview.vix_change:+.2f}% |"
            )

        return "\n".join(lines)

    def extract_hashtags_from_report(
        self,
        layer_4_content: str,
        watchlist_symbols: set = None,
        discovered_symbols: list = None,
    ) -> list[str]:
        """
        Extract stock tickers from Layer 4 content.
        Only returns tickers that are explicitly in watchlist or discovered in 4B section.

        Args:
            layer_4_content: The Layer 4 (Equity Signals) content
            watchlist_symbols: Set of watchlist stock symbols
            discovered_symbols: List of newly discovered symbols from 4B section

        Returns:
            List of ticker symbols (watchlist + discovered only)
        """
        tickers = []
        seen = set()

        # 1. Add watchlist symbols that appear in Layer 4 content
        if watchlist_symbols:
            for symbol in watchlist_symbols:
                # Check if symbol appears in content (with word boundary)
                if re.search(rf'\b{symbol}\b', layer_4_content):
                    if symbol not in seen:
                        tickers.append(symbol)
                        seen.add(symbol)

        # 2. Add discovered symbols from 4B section
        if discovered_symbols:
            for symbol in discovered_symbols:
                if symbol not in seen:
                    tickers.append(symbol)
                    seen.add(symbol)

        # 3. Try to extract tickers from 4B section if discovered_symbols not provided
        if not discovered_symbols:
            # Look for 4B section and extract tickers there
            section_4b_match = re.search(
                r'4B[:\s]*新發現.*?(?=###|$)',
                layer_4_content,
                re.DOTALL | re.IGNORECASE
            )
            if section_4b_match:
                section_4b = section_4b_match.group()
                # Pattern: $TICKER or (TICKER) or **TICKER**
                ticker_patterns = [
                    r'\$([A-Z]{1,5})\b',           # $AAPL
                    r'\(([A-Z]{1,5})\)',            # (AAPL)
                    r'\*\*([A-Z]{1,5})\*\*',       # **AAPL**
                    r'【([A-Z]{1,5})】',            # 【AAPL】
                ]
                for pattern in ticker_patterns:
                    matches = re.findall(pattern, section_4b)
                    for match in matches:
                        if match not in seen and len(match) >= 2:
                            tickers.append(match)
                            seen.add(match)

        return tickers[:15]  # Return top 15 tickers

    def generate_layered_report(
        self,
        yesterday_report: dict,
        news_items: list,
        market_overview,
        watchlist_stocks: list,
        sec_summary: str = "",
        fda_summary: str = "",
    ) -> LayeredReportResult:
        """
        Generate complete layered pre-market report.

        Uses 3-stage LLM calls:
        1. Hidden Layer + Layer 0-1 (~4000 tokens)
        2. Layer 2-3 (~2000 tokens)
        3. Layer 4-5 + News Summary (~3000 tokens)

        Args:
            yesterday_report: Dict from get_yesterday_pre_market()
            news_items: List of NewsItem objects
            market_overview: MarketOverview object
            watchlist_stocks: List of StockData objects
            sec_summary: Formatted SEC filings
            fda_summary: Formatted FDA updates

        Returns:
            LayeredReportResult with all layers and metadata
        """
        # Format input data
        news_data = "\n".join([
            f"- [{n.source}] {n.title}"
            for n in news_items[:50]
        ])

        market_data = self._format_market_data(market_overview)
        watchlist_data = self._format_watchlist_data(watchlist_stocks)

        # Stage 1: Hidden Layer processing
        print("   Processing Hidden Layer...")
        hidden_output = self.process_hidden_layer(
            yesterday_report=yesterday_report,
            news_data=news_data,
            sec_data=sec_summary,
            fda_data=fda_summary,
            market_data=market_data,
        )

        # Stage 2: Generate Layer 0-1
        print("   Generating Layer 0-1...")
        layer_0, layer_1 = self._generate_layer_0_1(
            hidden_layer_output=hidden_output,
            market_data=market_data,
            news_data=news_data,
        )

        # Stage 3: Generate Layer 2-3
        print("   Generating Layer 2-3...")
        layer_2, layer_3 = self._generate_layer_2_3(
            layer_0_content=layer_0,
            layer_1_content=layer_1,
            market_data=market_data,
        )

        # Stage 4: Generate Layer 4-5
        print("   Generating Layer 4-5...")
        company_changes = hidden_output.get("company_changes", [])
        layer_4, layer_5 = self._generate_layer_4_5(
            layer_0_content=layer_0,
            layer_1_content=layer_1,
            layer_2_content=layer_2,
            layer_3_content=layer_3,
            watchlist_data=watchlist_data,
            company_changes=company_changes,
        )

        # Stage 5: Generate News Summary
        print("   Generating news summary...")
        news_summary = self.generate_news_summary(
            news_data=news_data,
            market_data=market_data,
        )

        # Format market appendix
        market_appendix = self._format_market_appendix(market_overview)

        # Extract tickers from Layer 4 (only watchlist + discovered)
        watchlist_symbols = {s.symbol for s in watchlist_stocks} if watchlist_stocks else set()
        extracted_tickers = self.extract_hashtags_from_report(
            layer_4,
            watchlist_symbols=watchlist_symbols,
            discovered_symbols=None,  # Will be extracted from 4B section
        )

        return LayeredReportResult(
            layer_0=layer_0,
            layer_1=layer_1,
            layer_2=layer_2,
            layer_3=layer_3,
            layer_4=layer_4,
            layer_5=layer_5,
            news_summary=news_summary,
            market_appendix=market_appendix,
            hidden_layer_output=hidden_output,
            extracted_tickers=extracted_tickers,
        )

    def _format_market_data(self, overview) -> str:
        """Format market overview for prompts."""
        lines = []
        if overview.sp500:
            lines.append(f"S&P 500: {overview.sp500.current_price:,.2f} ({overview.sp500.change_percent:+.2f}%)")
        if overview.nasdaq:
            lines.append(f"NASDAQ: {overview.nasdaq.current_price:,.2f} ({overview.nasdaq.change_percent:+.2f}%)")
        if overview.dow:
            lines.append(f"Dow Jones: {overview.dow.current_price:,.2f} ({overview.dow.change_percent:+.2f}%)")
        if overview.vix:
            lines.append(f"VIX: {overview.vix:.2f} ({overview.vix_change:+.2f}%)")
        lines.append(f"市場情緒: {overview.market_sentiment}")
        return "\n".join(lines)

    def _format_watchlist_data(self, stocks: list) -> str:
        """Format watchlist stocks for prompts."""
        if not stocks:
            return "無觀察名單數據"

        lines = ["| 代碼 | 現價 | 漲跌幅 | RSI | 趨勢 |"]
        lines.append("|------|------|--------|-----|------|")

        for stock in stocks[:30]:  # Limit to 30 stocks
            rsi = f"{stock.rsi_14:.0f}" if stock.rsi_14 else "N/A"
            lines.append(
                f"| {stock.symbol} | ${stock.current_price:,.2f} | "
                f"{stock.change_percent:+.2f}% | {rsi} | {stock.trend} |"
            )

        return "\n".join(lines)
