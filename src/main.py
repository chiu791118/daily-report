#!/usr/bin/env python3
"""
Daily Report 2.0 - Main Entry Point

Usage:
    python main.py pre-market    # Generate pre-market report (18:00 Taiwan, Mon-Fri)
    python main.py test          # Test all collectors and analyzers
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytz

from google import genai
from google.genai import types

from src.config.settings import (
    TIMEZONE,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    NOTION_API_KEY,
    NOTION_DATABASE_ID,
    US_EASTERN_TZ,
)
from src.collectors import NewsCollector, StockCollector
from src.collectors.sec_edgar import SECEdgarCollector
from src.collectors.fda import FDACollector
from src.collectors.economic_calendar import EconomicCalendarCollector
from src.collectors.earnings import EarningsCalendarCollector
from src.collectors.universe import UniverseCollector
from src.analyzers.pre_market_v3 import PreMarketV3Analyzer
from src.outputs import MarkdownReportGenerator, NotionPublisher


def check_api_keys():
    """Check if required API keys are set."""
    missing = []

    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if not NOTION_API_KEY or not NOTION_DATABASE_ID:
        missing.append("NOTION_API_KEY/NOTION_DATABASE_ID")

    if missing:
        print("⚠️  Missing required API keys:")
        for key in missing:
            print(f"   - {key}")
        print("\nPlease set these in your .env file.")
        return False

    return True


def _collect_sec_summary(hours_lookback: int, max_filings: int) -> str:
    """Collect recent SEC 8-K filings and return formatted markdown. Empty string on error."""
    try:
        print("📋 Collecting SEC 8-K filings...")
        sec_collector = SECEdgarCollector()
        filings = sec_collector.collect_recent_filings(
            form_types=["8-K"],
            hours_lookback=hours_lookback,
            max_per_type=max_filings,
        )
        if not filings:
            print("   No recent 8-K filings found")
            return ""
        print(f"   Found {len(filings)} recent 8-K filings")
        lines = ["### 📋 近期 SEC 8-K 公告\n"]
        for filing in filings[:10]:
            items_str = ", ".join(filing.metadata.get("items", [])[:2]) if filing.metadata.get("items") else ""
            lines.append(f"- **{filing.title}** {f'({items_str})' if items_str else ''}")
        return "\n".join(lines)
    except Exception as e:
        print(f"   ⚠️ SEC collection error: {e}")
        return ""


def _collect_fda_summary(days_lookback: int, max_results: int) -> str:
    """Collect recent FDA updates and return formatted markdown. Empty string on error."""
    try:
        print("🏥 Collecting FDA updates...")
        fda_collector = FDACollector()
        updates = fda_collector.collect_all(days_lookback=days_lookback, max_results=max_results)
        if not updates:
            print("   No recent FDA updates")
            return ""
        print(f"   Found {len(updates)} FDA updates")
        lines = ["### 🏥 FDA 最新動態\n"]
        for update in updates[:5]:
            lines.append(f"- **[{update.category}]** {update.title}")
            if update.summary and update.summary.strip() != update.title.strip():
                summary_text = update.summary[:150] + "..." if len(update.summary) > 150 else update.summary
                lines.append(f"  - {summary_text}")
        return "\n".join(lines)
    except Exception as e:
        print(f"   ⚠️ FDA collection error: {e}")
        return ""


def _translate_fda_summary(fda_summary: str) -> str:
    """Add Chinese translations to FDA summary entries."""
    if not fda_summary or not GEMINI_API_KEY:
        return fda_summary
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            "將以下 FDA 動態的英文內容翻譯為繁體中文。"
            "保持原有 markdown 格式，在每個英文項目後面換行加上「  → （中文翻譯）」。"
            "只輸出結果，不要其他說明。\n\n"
            f"{fda_summary}"
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=1500),
        )
        return response.text.strip()
    except Exception as e:
        print(f"   ⚠️ FDA translation error: {e}")
        return fda_summary


def _build_regulatory_updates(sec_summary: str, fda_summary: str) -> str:
    """Combine SEC and FDA summaries into a single regulatory section."""
    parts = [s for s in [sec_summary, fda_summary] if s]
    return "\n\n".join(parts)


def generate_pre_market_report():
    """
    Generate pre-market report V3 (focused briefing format).
    """
    print("\n" + "="*60)
    print("📈 Generating Pre-Market Report V3")
    print("="*60)

    tz_tw = pytz.timezone(TIMEZONE)
    tz_et = pytz.timezone(US_EASTERN_TZ)
    now_tw = datetime.now(tz_tw)
    now_et = now_tw.astimezone(tz_et)

    date_tw_str = now_tw.strftime("%Y-%m-%d")
    date_et = now_et.date()
    print(f"Time: {now_et.strftime('%Y-%m-%d %H:%M')} (ET) / {now_tw.strftime('%Y-%m-%d %H:%M')} ({TIMEZONE})\n")

    # Initialize components
    news_collector = NewsCollector()
    stock_collector = StockCollector()
    report_generator = MarkdownReportGenerator()

    # Collect news
    print("📰 Collecting news...")
    news_items = news_collector.collect_all()
    print(f"   Found {len(news_items)} news items")

    # Market overview
    print("\n📊 Fetching market data...")
    market_overview = stock_collector.get_market_overview()

    # Watchlist
    print("📋 Fetching watchlist...")
    all_stocks = stock_collector.collect_watchlist()
    print(f"   Collected {len(all_stocks)} stocks")

    # Economic calendar
    print("\n🗓️  Fetching economic calendar...")
    econ_collector = EconomicCalendarCollector()
    econ_events = econ_collector.get_events_for_date(date_et)
    econ_rows = econ_collector.to_report_rows(econ_events)
    if econ_collector.last_warning:
        print(f"   ⚠️ {econ_collector.last_warning}")
    else:
        print(f"   Found {len(econ_events)} economic events")

    # Earnings calendar
    print("\n💼 Fetching earnings calendar...")
    earnings_collector = EarningsCalendarCollector()
    earnings_events = earnings_collector.get_events_for_date(date_et)
    earnings_rows = earnings_collector.to_report_rows(earnings_events)
    if earnings_collector.last_warning:
        print(f"   ⚠️ {earnings_collector.last_warning}")
    else:
        print(f"   Found {len(earnings_events)} earnings events")

    # Universe for event-driven tickers
    print("\n🌐 Building universe...")
    universe_collector = UniverseCollector()
    universe_data = universe_collector.get_universe()
    if universe_collector.last_warning:
        print(f"   ⚠️ {universe_collector.last_warning}")
    else:
        print(f"   Universe size: {len(universe_data.tickers)} tickers")

    # Collect SEC and FDA (past 48 hours for pre-market)
    print()
    sec_summary = _collect_sec_summary(hours_lookback=48, max_filings=20)
    fda_summary = _collect_fda_summary(days_lookback=2, max_results=10)
    if fda_summary:
        print("🌐 Translating FDA updates...")
        fda_summary = _translate_fda_summary(fda_summary)
    regulatory_updates = _build_regulatory_updates(sec_summary, fda_summary)

    # Fetch yesterday's pre-market report for hidden layer comparison
    print("\n📖 Fetching yesterday's pre-market report...")
    notion_publisher = NotionPublisher()
    yesterday_report = notion_publisher.get_yesterday_pre_market(date_tw_str)
    if yesterday_report["available"]:
        print(f"   Found: {yesterday_report['date']} ({yesterday_report['source']})")
    else:
        print(f"   {yesterday_report['fallback_note']}")

    # Generate report sections with LLM
    print("\n🤖 Generating V3 sections...")
    analyzer = PreMarketV3Analyzer()
    sections, meta = analyzer.generate_sections(
        market_overview=market_overview,
        economic_events=econ_events,
        earnings_events=earnings_events,
        news_items=news_items,
        watchlist_stocks=all_stocks,
        universe_data=universe_data,
        yesterday_report=yesterday_report,
        sec_summary=sec_summary,
        fda_summary=fda_summary,
    )

    # Generate final report
    print("\n📝 Generating final report...")
    report = report_generator.generate_pre_market_report_v3(
        sections=sections,
        market_overview=market_overview,
        economic_rows=econ_rows,
        earnings_rows=earnings_rows,
        news_digest=meta.get("news_digest", []),
        yesterday_changes=meta.get("yesterday_changes"),
        regulatory_updates=regulatory_updates,
        economic_note=econ_collector.last_warning,
        earnings_note=earnings_collector.last_warning,
    )

    # Upload to Notion
    print("\n📤 Uploading to Notion...")
    title_date = now_tw.strftime("%y%m%d")
    title = f"{title_date}_Pre-market"

    tags = [item.get("symbol") for item in sections.get("watchlist_focus", []) if item.get("symbol")]
    tags += [item.get("symbol") for item in sections.get("event_driven", []) if item.get("symbol")]
    tags = tags[:10]
    print(f"   Tags: {tags}")
    # notion_publisher already initialized above
    page_url = notion_publisher.create_daily_page(
        title=title,
        content=report,
        report_type="pre-market",
        date_str=date_tw_str,
        tags=tags,
    )
    print(f"\n✅ Pre-market report V3 uploaded to Notion: {page_url}")

    return page_url


def test_components():
    """Test all components without generating full reports."""
    print("\n" + "="*60)
    print("🧪 Testing Components")
    print("="*60)

    # Test News Collector
    print("\n1️⃣ Testing News Collector...")
    try:
        collector = NewsCollector()
        news = collector.collect_all()
        print(f"   ✅ Collected {len(news)} news items")

        # Show source breakdown
        by_source = {}
        for item in news:
            by_source[item.source] = by_source.get(item.source, 0) + 1
        print("   Sources:")
        for source, count in sorted(by_source.items(), key=lambda x: -x[1]):
            print(f"      {source}: {count}")

        # Show ticker mentions
        ticker_news = [n for n in news if n.related_tickers]
        print(f"   News with ticker mentions: {len(ticker_news)}")

    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test Stock Collector
    print("\n2️⃣ Testing Stock Collector...")
    try:
        collector = StockCollector()
        overview = collector.get_market_overview()
        print(f"   ✅ Market overview fetched")
        if overview.sp500:
            print(f"   S&P 500: {overview.sp500.current_price:,.2f} ({overview.sp500.change_percent:+.2f}%)")

        stocks = collector.collect_watchlist()
        print(f"   ✅ Collected {len(stocks)} stocks from watchlist")

        # Show big movers
        movers = [s for s in stocks if abs(s.change_percent) >= 3]
        if movers:
            print(f"   Big movers (>=3%):")
            for s in sorted(movers, key=lambda x: abs(x.change_percent), reverse=True)[:5]:
                print(f"      {s.symbol}: {s.change_percent:+.2f}%")

    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test AI Analyzers
    print("\n3️⃣ Testing AI Analyzers...")
    if GEMINI_API_KEY:
        try:
            analyzer = PreMarketV3Analyzer()
            print("   ✅ PreMarketV3Analyzer initialized")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    else:
        print("   ⚠️ Skipped (GEMINI_API_KEY not set)")

    print("\n" + "="*60)
    print("✅ Component testing complete")
    print("="*60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Daily Market Digest - Automated market analysis tool",
    )

    parser.add_argument(
        "command",
        choices=["pre-market", "test"],
        help="Report type to generate",
    )

    args = parser.parse_args()

    # Check API keys for non-test commands
    if args.command != "test" and not check_api_keys():
        sys.exit(1)

    try:
        if args.command == "pre-market":
            generate_pre_market_report()

        elif args.command == "test":
            test_components()

    except KeyboardInterrupt:
        print("\n\n⚠️ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
