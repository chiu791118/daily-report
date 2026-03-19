"""
Markdown Output Module
Generates markdown reports for market digest.
"""
from datetime import datetime
from pathlib import Path
import pytz

from src.config.settings import REPORTS_DIR, TIMEZONE

# Default tomorrow focus content (defined outside f-string for Python 3.9 compatibility)
DEFAULT_TOMORROW_FOCUS = """- 持續關注財報季動態
- 留意聯準會官員發言
- 觀察技術面支撐壓力位"""


class MarkdownReportGenerator:
    """Generates markdown reports."""

    def __init__(self):
        self.tz = pytz.timezone(TIMEZONE)

    def save_report_to_date(self, content: str, report_type: str, date_str: str) -> Path:
        """Save report to a specific date folder."""
        # Create date directory
        date_dir = REPORTS_DIR / date_str
        date_dir.mkdir(parents=True, exist_ok=True)

        # Determine filename
        filename = f"{report_type}.md"
        filepath = date_dir / filename

        # Write file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"Report saved to: {filepath}")
        return filepath

    def _sentiment_emoji(self, sentiment: str) -> str:
        """Get emoji for sentiment (Chinese stock convention: red=up, green=down)."""
        emoji_map = {
            "bullish": "🔴",
            "bearish": "🟢",
            "neutral": "🟡",
            "unknown": "⚪",
        }
        return emoji_map.get(sentiment.lower(), "⚪")

    def save_report(self, content: str, report_type: str) -> Path:
        """Save report to file."""
        now = datetime.now(self.tz)
        date_str = now.strftime("%Y-%m-%d")

        # Create date directory
        date_dir = REPORTS_DIR / date_str
        date_dir.mkdir(parents=True, exist_ok=True)

        # Determine filename
        filename = f"{report_type}.md"
        filepath = date_dir / filename

        # Write file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"Report saved to: {filepath}")
        return filepath

    def generate_simple_report(
        self,
        title: str,
        sections: dict[str, str],
    ) -> str:
        """Generate a simple report with custom sections."""
        now = datetime.now(self.tz)

        lines = [
            f"# {title}",
            "",
            f"**生成時間:** {now.strftime('%Y-%m-%d %H:%M')} (台北時間)",
            "",
            "---",
            "",
        ]

        for section_title, content in sections.items():
            lines.extend([
                f"## {section_title}",
                "",
                content,
                "",
                "---",
                "",
            ])

        lines.append("*生成工具: Daily Market Digest*")

        return "\n".join(lines)

    def generate_pre_market_report_v3(
        self,
        sections: dict,
        market_overview,
        economic_rows: list,
        earnings_rows: list,
        news_digest: list,
        yesterday_changes: dict = None,
        regulatory_updates: str = "",
        economic_note: str = "",
        earnings_note: str = "",
    ) -> str:
        """Generate pre-market report V3 with a focused briefing structure."""
        tz_et = pytz.timezone("US/Eastern")
        now_tw = datetime.now(self.tz)
        now_et = now_tw.astimezone(tz_et)

        date_tw = now_tw.strftime("%Y-%m-%d")
        date_et = now_et.strftime("%Y-%m-%d")

        # Sections
        es = self._format_numbered(sections.get("executive_summary", []), 3)
        market_snapshot = self._format_market_snapshot(market_overview)
        economic_section = self._format_economic_calendar(economic_rows, economic_note)
        earnings_section = self._format_earnings_calendar(earnings_rows, earnings_note)
        changes_section = self._format_yesterday_changes(yesterday_changes)
        watchlist_focus = self._format_watchlist_table(sections.get("watchlist_focus", []))
        event_driven = self._format_event_driven_table(sections.get("event_driven", []))
        news_digest_section = self._format_news_digest(news_digest)

        regulatory_section = ""
        if regulatory_updates:
            regulatory_section = f"\n### 監管動態\n\n{regulatory_updates}\n"

        report = f"""# 盤前簡報

**{date_et} (ET) / {date_tw} (台北)** | {now_et.strftime('%H:%M')} ET / {now_tw.strftime('%H:%M')} 台北

---

## ES | Executive Summary

{es}

---

## 市場快照

{market_snapshot}
---

## 今日日程

### 經濟數據

{economic_section}

### 財報

{earnings_section}

---

## 昨日→今日 變化信號

{changes_section}

---

## Watch List

{watchlist_focus}

---

## 事件驅動

{event_driven}

---

## 參考資料

### 新聞

{news_digest_section}

{regulatory_section}
---
*Daily Report | {date_tw}*
"""
        return report

    def _format_yesterday_changes(self, changes: dict) -> str:
        """Format hidden layer output for direct display."""
        if not changes:
            return "昨日報告不可用，無法進行變化比較。"

        lines = []

        # Group by type
        for change_type, label in [("反轉", "反轉信號"), ("新發現", "新發現"), ("延續", "延續")]:
            items = []
            for c in changes.get("macro_changes", []):
                if c.get("type") == change_type:
                    assets = ", ".join(c.get("related_assets", []))
                    items.append(f"[宏觀] {c.get('summary', '')} → {c.get('impact', '')}" + (f" ({assets})" if assets else ""))
            for c in changes.get("industry_changes", []):
                if c.get("type") == change_type:
                    tickers = ", ".join(c.get("related_tickers", []))
                    items.append(f"[{c.get('industry', '行業')}] {c.get('summary', '')} → {c.get('impact', '')}" + (f" ({tickers})" if tickers else ""))
            for c in changes.get("company_changes", []):
                if c.get("type") == change_type:
                    items.append(f"[{c.get('ticker', '')}] {c.get('summary', '')} — {c.get('catalyst', '')} ({c.get('action_signal', '')})")

            if items:
                lines.append(f"**{label}：**")
                for item in items:
                    lines.append(f"- {item}")
                lines.append("")

        if not lines:
            return "今日無顯著變化信號。"

        return "\n".join(lines)

    def _format_economic_calendar(self, rows: list, note: str = "") -> str:
        if not rows:
            return note or "今日無重大經濟數據公布。"

        lines = [
            "| 時間(ET) | 時間(台北) | 國家 | 指標 | 重要性 | 預期 | 前值 |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in rows[:15]:
            importance = row.get("importance")
            importance_str = "" if importance is None else ("★" * int(importance))
            lines.append(
                f"| {row.get('time_et','')} | {row.get('time_taipei','')} | {row.get('country','')} | "
                f"{row.get('event','')} | {importance_str} | {row.get('forecast','—') or '—'} | "
                f"{row.get('previous','—') or '—'} |"
            )
        return "\n".join(lines)

    def _format_earnings_calendar(self, rows: list, note: str = "") -> str:
        if not rows:
            return note or "今日無重大財報公布。"

        lines = [
            "| 代碼 | 公司 | 時間(ET) | 時間(台北) | EPS 預期 | 營收預期 |",
            "|---|---|---|---|---|---|",
        ]
        for row in rows[:20]:
            lines.append(
                f"| {row.get('symbol','')} | {row.get('company','')} | {row.get('time_et','')} | "
                f"{row.get('time_taipei','')} | {row.get('eps_estimate','—') or '—'} | "
                f"{row.get('revenue_estimate','—') or '—'} |"
            )
        return "\n".join(lines)

    def _format_market_snapshot(self, overview) -> str:
        lines = []
        if overview.sp500:
            color = "🔴" if overview.sp500.change_percent >= 0 else "🟢"
            lines.append(f"- {color} S&P 500: {overview.sp500.current_price:,.2f} ({overview.sp500.change_percent:+.2f}%)")
        if overview.nasdaq:
            color = "🔴" if overview.nasdaq.change_percent >= 0 else "🟢"
            lines.append(f"- {color} NASDAQ: {overview.nasdaq.current_price:,.2f} ({overview.nasdaq.change_percent:+.2f}%)")
        if overview.dow:
            color = "🔴" if overview.dow.change_percent >= 0 else "🟢"
            lines.append(f"- {color} Dow Jones: {overview.dow.current_price:,.2f} ({overview.dow.change_percent:+.2f}%)")
        if overview.vix is not None:
            vix_chg = overview.vix_change or 0
            # VIX is inverse: VIX up = bearish (green), VIX down = bullish (red)
            color = "🟢" if vix_chg >= 0 else "🔴"
            lines.append(f"- {color} VIX: {overview.vix:.2f} ({vix_chg:+.2f}%)")
        if overview.market_sentiment:
            emoji = self._sentiment_emoji(overview.market_sentiment)
            lines.append(f"- {emoji} 市場情緒: {overview.market_sentiment}")
        if not lines:
            return "- 市場數據不足\n"
        return "\n".join(lines) + "\n"

    def _format_numbered(self, items: list, expected: int) -> str:
        if not items:
            return "無資料"
        lines = []
        for i, item in enumerate(items[:expected], 1):
            lines.append(f"{i}. {item}")
        return "\n".join(lines)

    def _format_bullets(self, items: list) -> str:
        if not items:
            return "無資料"
        return "\n".join([f"- {i}" for i in items])

    def _format_watchlist_table(self, items: list) -> str:
        if not items:
            return "今日無需特別關注的觀察清單標的。"
        lines = [
            "| 代碼 | 觸發原因 | 今日觀察點 |",
            "|---|---|---|",
        ]
        for item in items[:8]:
            lines.append(
                f"| {item.get('symbol','')} | {item.get('why','')} | {item.get('watch','')} |"
            )
        return "\n".join(lines)

    def _format_event_driven_table(self, items: list) -> str:
        if not items:
            return "今日無清單外事件驅動標的。"
        lines = [
            "| 代碼 | 事件 | 潛在影響 |",
            "|---|---|---|",
        ]
        for item in items[:8]:
            lines.append(
                f"| {item.get('symbol','')} | {item.get('why','')} | {item.get('impact','')} |"
            )
        return "\n".join(lines)

    def _format_news_digest(self, news_items: list) -> str:
        if not news_items:
            return "無新聞資料。"
        lines = []
        for item in news_items[:12]:
            time_part = ""
            if item.get("time_et") and item.get("time_taipei"):
                time_part = f" ({item.get('time_et')} ET / {item.get('time_taipei')} 台北)"
            lines.append(f"- [{item.get('source','')}] {item.get('title','')}{time_part}")
        return "\n".join(lines)



    def generate_pre_market_report_v4(
        self,
        sections: dict,
        market_overview,
        economic_rows: list,
        earnings_rows: list,
        news_digest: list,
        regulatory_updates: str = "",
        economic_note: str = "",
        earnings_note: str = "",
    ) -> str:
        """Generate pre-market report V4 (A+D hybrid style)."""
        tz_et = pytz.timezone("US/Eastern")
        now_tw = datetime.now(self.tz)
        now_et = now_tw.astimezone(tz_et)

        date_tw = now_tw.strftime("%Y-%m-%d")
        date_et = now_et.strftime("%Y-%m-%d")

        # --- Build each section ---
        es = self._v4_executive_summary(sections.get("executive_summary", []))
        macro = self._v4_macro_assessment(sections.get("macro_assessment", {}))
        fda = self._v4_fda_highlights(sections.get("fda_highlights", []))
        news = self._v4_news_must_read(sections.get("news_analysis", {}))
        market_snapshot = self._format_market_snapshot(market_overview)
        allocation = self._v4_allocation_signals(sections.get("allocation_signals", []))
        economic_section = self._format_economic_calendar(economic_rows, economic_note)
        earnings_section = self._format_earnings_calendar(earnings_rows, earnings_note)
        watchlist = self._v4_watchlist_analysis(sections.get("watchlist_analysis", []))
        themes = self._v4_theme_radar(sections.get("theme_radar", []))
        anomalies = self._v4_anomaly_tickers(sections.get("anomaly_tickers", []))
        changes = self._format_yesterday_changes(sections.get("yesterday_changes"))
        news_ref = self._format_news_digest(news_digest)

        regulatory_section = ""
        if regulatory_updates:
            regulatory_section = f"\n### 監管公告原文\n\n{regulatory_updates}\n"

        report = f"""# 盤前簡報

**{date_et} (ET) / {date_tw} (台北)** | {now_et.strftime('%H:%M')} ET / {now_tw.strftime('%H:%M')} 台北

---

## 1. Executive Summary

{es}

---

## 2. 宏觀與地緣

{macro}

---

## 3. FDA / 醫藥動態

{fda}

---

## 4. 今日必讀

{news}

---

## 5. 市場快照 & 配置信號

### 市場數據

{market_snapshot}
### 資產配置信號

{allocation}

---

## 6. 觀察清單

{watchlist}

---

## 7. 新發現 & 主題雷達

### 主題雷達

{themes}

### 異常標的

{anomalies}

---

## 8. 今日日程

### 經濟數據

{economic_section}

### 財報

{earnings_section}

---

## 9. 昨日→今日 變化信號

{changes}

---

## 參考資料

### 新聞清單

{news_ref}

{regulatory_section}
---
*Daily Report V4 | {date_tw}*
"""
        return report

    # ------------------------------------------------------------------
    # V4 section formatters
    # ------------------------------------------------------------------

    def _v4_executive_summary(self, items: list) -> str:
        if not items:
            return "無資料"
        lines = []
        for i, item in enumerate(items[:5], 1):
            if isinstance(item, dict):
                dimension = item.get("dimension", "")
                fact = item.get("fact", "")
                reasoning = item.get("reasoning", "")
                action = item.get("action", "")
                falsification = item.get("falsification", "")

                lines.append(f"**{i}. {dimension}**")
                if fact:
                    lines.append(f"- 【事實】{fact}")
                if reasoning:
                    lines.append(f"- 【推論】{reasoning}")
                if action:
                    lines.append(f"- 【行動】{action}")
                if falsification:
                    lines.append(f"- 【失效】{falsification}")
            else:
                # Fallback: plain string (backward compatible)
                lines.append(f"**{i}.** {item}")
            lines.append("")
        return "\n".join(lines)

    def _v4_macro_assessment(self, macro: dict) -> str:
        if not macro:
            return "無宏觀評估資料。"

        lines = []
        for key, label in [("monetary", "💰 貨幣環境"), ("geopolitical", "🌍 地緣政治"), ("growth", "📈 成長動能")]:
            section = macro.get(key, {})
            if not section:
                continue
            status = section.get("status", "")
            logic = section.get("logic", "") or section.get("summary", "")
            key_data = section.get("key_data", "")
            transmission = section.get("transmission", "")
            impact = section.get("impact", "")
            watch = section.get("watch", "")
            flip = section.get("flip_condition", "")

            lines.append(f"**{label}**" + (f"：{status}" if status else ""))
            if logic:
                lines.append(f"- {logic}")
            if key_data:
                lines.append(f"- 關鍵數據：{key_data}")
            if transmission:
                lines.append(f"- 傳導通道：{transmission}")
            if impact:
                lines.append(f"- 影響判斷：{impact}")
            if watch:
                lines.append(f"- 📌 觀察點：{watch}")
            if flip:
                lines.append(f"- ⚠️ 翻轉條件：{flip}")
            lines.append("")

        return "\n".join(lines) if lines else "無宏觀評估資料。"

    def _v4_fda_highlights(self, items: list) -> str:
        if not items:
            return "今日無重要 FDA 動態。"

        lines = []
        for item in items:
            event = item.get("event", "")
            fda_type = item.get("type", "")
            indication = item.get("indication", "")
            impact = item.get("structural_impact", "")
            tickers = ", ".join(item.get("tickers", []))
            signal = item.get("signal", "")

            signal_emoji = {"利好": "🟢", "利空": "🔴", "中性": "🟡"}.get(signal, "⚪")

            lines.append(f"**{signal_emoji} [{fda_type}] {event}**")
            if indication:
                lines.append(f"- 適應症/領域：{indication}")
            if impact:
                lines.append(f"- 結構性影響：{impact}")
            if tickers:
                lines.append(f"- 相關標的：{tickers}")
            lines.append("")

        return "\n".join(lines)

    def _v4_news_must_read(self, news_analysis: dict) -> str:
        if not news_analysis:
            return "無新聞分析資料。"

        lines = []
        for key, label in [
            ("macro_policy", "🏛️ 宏觀 / 政策"),
            ("tech_ai", "⚡ 科技 / AI"),
            ("industry_company", "🏢 產業 / 公司"),
            ("pharma_fda", "💊 醫藥 / FDA"),
        ]:
            items = news_analysis.get(key, [])
            if not items:
                continue

            lines.append(f"### {label}")
            lines.append("")
            for item in items:
                headline = item.get("headline", "")
                fact = item.get("fact", "")
                so_what = item.get("so_what", "")
                falsification = item.get("falsification", "")
                tickers = ", ".join(item.get("tickers", []))
                paradigm = item.get("paradigm_shift", False)

                title_line = f"**{headline}**"
                if tickers:
                    title_line += f" ({tickers})"
                if paradigm:
                    title_line += " 🔺範式轉移"
                lines.append(title_line)

                if fact:
                    lines.append(f"  【事實】{fact}")
                if so_what:
                    lines.append(f"  【推論】{so_what}")
                if falsification:
                    lines.append(f"  【失效條件】{falsification}")
                lines.append("")

        return "\n".join(lines) if lines else "無新聞分析資料。"

    def _v4_allocation_signals(self, items: list) -> str:
        if not items:
            return "無配置信號資料。"

        lines = [
            "| 資產類別 | 信號 | 建議 | 邏輯 | 翻轉條件 |",
            "|---------|------|------|------|----------|",
        ]
        for item in items:
            lines.append(
                f"| {item.get('asset','')} | {item.get('signal','')} | "
                f"{item.get('action','')} | {item.get('logic','')} | "
                f"{item.get('flip_condition','')} |"
            )
        return "\n".join(lines)

    def _v4_watchlist_analysis(self, items: list) -> str:
        if not items:
            return "今日觀察清單無信號觸發。"

        lines = []
        for item in items:
            symbol = item.get("symbol", "")
            name = item.get("name", "")
            price = item.get("price", "")
            change = item.get("change_pct", "")
            signal_type = item.get("signal_type", "")
            analysis = item.get("analysis", "")
            action = item.get("action", "")
            timeframe = item.get("timeframe", "")
            priority = item.get("priority", "")

            priority_emoji = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(priority, "")

            header = f"**{priority_emoji} {symbol}**"
            if name:
                header += f" ({name})"
            if price:
                header += f" — ${price}"
            if change:
                header += f" ({change:+.2f}%)" if isinstance(change, (int, float)) else f" ({change})"
            if signal_type:
                header += f" [{signal_type}]"

            lines.append(header)
            if analysis:
                lines.append(f"  {analysis}")
            if action:
                lines.append(f"  → **操作建議：{action}**")
            if timeframe:
                lines.append(f"  ⏱ 時間框架：{timeframe}")
            lines.append("")

        return "\n".join(lines)

    def _v4_theme_radar(self, items: list) -> str:
        if not items:
            return "今日無新興主題。"

        lines = []
        for item in items:
            theme = item.get("theme", "")
            why_now = item.get("why_now", "") or item.get("description", "")
            thesis = item.get("thesis", "")
            tickers = ", ".join(item.get("tickers", []))
            notes = item.get("ticker_notes", "")
            disproof = item.get("disproof", "")
            conviction = item.get("conviction", "")

            conv_emoji = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(conviction, "")

            lines.append(f"**{conv_emoji} {theme}**")
            if why_now:
                lines.append(f"  Why now：{why_now}")
            if thesis:
                lines.append(f"  投資假說：{thesis}")
            if tickers:
                lines.append(f"  相關標的：{tickers}")
            if notes:
                lines.append(f"  {notes}")
            if disproof:
                lines.append(f"  ⚠️ 失效條件：{disproof}")
            lines.append("")

        return "\n".join(lines)

    def _v4_anomaly_tickers(self, items: list) -> str:
        if not items:
            return "今日無異常標的。"

        lines = []
        for item in items:
            symbol = item.get("symbol", "")
            reason = item.get("reason", "")
            news = item.get("news_link", "")
            fundamental = item.get("fundamental_check", "")
            worth = item.get("worth_watching", "")

            lines.append(f"**{symbol}**")
            if reason:
                lines.append(f"  異常原因：{reason}")
            if news:
                lines.append(f"  相關新聞：{news}")
            if fundamental:
                lines.append(f"  基本面校驗：{fundamental}")
            if worth:
                lines.append(f"  → {worth}")
            lines.append("")

        return "\n".join(lines)

def main():
    """Test the markdown generator."""
    generator = MarkdownReportGenerator()

    # Test simple report
    report = generator.generate_simple_report(
        title="測試報告",
        sections={
            "📰 新聞摘要": "今日市場波動較大...",
            "📊 市場數據": "S&P 500: 5,000.00 (+0.5%)",
            "📝 備註": "這是測試內容",
        },
    )

    print(report)

    # Save test report
    filepath = generator.save_report(report, "test-report")
    print(f"\nSaved to: {filepath}")


if __name__ == "__main__":
    main()
