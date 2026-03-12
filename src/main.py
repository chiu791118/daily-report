#!/usr/bin/env python3
"""
Daily Market Digest - Main Entry Point

Automated tool for generating daily market analysis reports.
Integrates news, YouTube content, and stock data with AI analysis.

Usage:
    python main.py pre-market    # Generate pre-market report (21:00 Taiwan)
    python main.py post-market   # Generate post-market report (05:00 Taiwan)
    python main.py saturday      # Generate Saturday industry report (09:00 Taiwan)
    python main.py sunday        # Generate Sunday outlook report (18:00 Taiwan)
    python main.py test          # Test all collectors and analyzers
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytz

from src.config.settings import (
    TIMEZONE,
    GEMINI_API_KEY,
    NOTION_API_KEY,
    NOTION_DATABASE_ID,
    REPORTS_DIR,
    US_EASTERN_TZ,
)
from src.collectors import NewsCollector, StockCollector
from src.collectors.sec_edgar import SECEdgarCollector
from src.collectors.fda import FDACollector
from src.collectors.economic_calendar import EconomicCalendarCollector
from src.collectors.earnings import EarningsCalendarCollector
from src.collectors.universe import UniverseCollector
from src.collectors.intel_aggregator import IntelAggregator
from src.analyzers import StockAnalyzer
from src.analyzers.pre_market_v3 import PreMarketV3Analyzer
from src.analyzers.industry_analyzer import IndustryAnalyzer
from src.outputs import MarkdownReportGenerator, NotionPublisher
from src.utils.trading_days import get_previous_trading_day


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


def extract_tickers_from_report(report_content: str, all_symbols: set) -> list[str]:
    """
    Extract stock tickers mentioned in the report content.
    Returns tickers sorted by frequency of mention.
    """
    import re
    from collections import Counter

    # Find all potential ticker mentions (uppercase 1-5 letter words)
    # Match patterns like: AAPL, $AAPL, **AAPL**, AAPL:, (AAPL)
    pattern = r'(?:^|[\s\$\*\(\|])([A-Z]{1,5})(?:[\s\*\)\|\:\,\.]|$)'
    matches = re.findall(pattern, report_content)

    # Count only tickers that are in our watchlist
    ticker_counts = Counter()
    for match in matches:
        if match in all_symbols:
            ticker_counts[match] += 1

    # Return top tickers sorted by frequency
    return [ticker for ticker, _ in ticker_counts.most_common(15)]


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
            if update.summary:
                summary_text = update.summary[:150] + "..." if len(update.summary) > 150 else update.summary
                lines.append(f"  - {summary_text}")
        return "\n".join(lines)
    except Exception as e:
        print(f"   ⚠️ FDA collection error: {e}")
        return ""


def _build_regulatory_updates(sec_summary: str, fda_summary: str) -> str:
    """Combine SEC and FDA summaries into a single regulatory section."""
    parts = [s for s in [sec_summary, fda_summary] if s]
    return "\n\n".join(parts)


def _format_weekly_market_summary(market_overview) -> str:
    """Format market overview indices for weekly reports (Saturday/Sunday)."""
    lines = []
    if market_overview.sp500:
        weekly = f" (本週 {market_overview.sp500.change_1w:+.2f}%)" if market_overview.sp500.change_1w else ""
        lines.append(f"- S&P 500: {market_overview.sp500.current_price:,.2f}{weekly}")
    if market_overview.nasdaq:
        weekly = f" (本週 {market_overview.nasdaq.change_1w:+.2f}%)" if market_overview.nasdaq.change_1w else ""
        lines.append(f"- NASDAQ: {market_overview.nasdaq.current_price:,.2f}{weekly}")
    if market_overview.dow:
        weekly = f" (本週 {market_overview.dow.change_1w:+.2f}%)" if market_overview.dow.change_1w else ""
        lines.append(f"- Dow Jones: {market_overview.dow.current_price:,.2f}{weekly}")
    if market_overview.vix:
        lines.append(f"- VIX: {market_overview.vix:.2f}")
    return "\n".join(lines)


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
        regulatory_updates=regulatory_updates,
        economic_note=econ_collector.last_warning,
        earnings_note=earnings_collector.last_warning,
    )

    # Upload to Notion
    print("\n📤 Uploading to Notion...")
    title_date = now_tw.strftime("%y%m%d")
    title = f"{title_date}_Pre-market"

    tags = (meta.get("watchlist_focus_symbols", []) + meta.get("event_driven_symbols", []))[:10]
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


def generate_post_market_report():
    """Generate post-market report (review of trading day, comparison with pre-market)."""
    print("\n" + "="*60)
    print("📉 Generating Post-Market Report")
    print("="*60)

    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    print(f"Time: {now.strftime('%Y-%m-%d %H:%M')} ({TIMEZONE})\n")

    # Post-market 報告永遠報告「前一個交易日」的結果
    trading_day = get_previous_trading_day(now)
    trading_date = trading_day.strftime("%Y-%m-%d")

    print(f"📅 美股交易日: {trading_date} (報告生成於 {now.strftime('%Y-%m-%d %H:%M')})")

    # 讀取盤前報告 (優先從 Notion，其次從本地檔案)
    pre_market_content = ""
    notion_publisher = None

    # 1. 嘗試從 Notion 讀取
    print("📖 Fetching pre-market report from Notion...")
    try:
        notion_publisher = NotionPublisher()
        pre_market_content = notion_publisher.get_pre_market_content(trading_date)
    except Exception as e:
        print(f"   ⚠️ Notion read error: {e}")
        notion_publisher = None

    # 2. 如果 Notion 沒有，嘗試本地檔案
    if not pre_market_content:
        pre_market_path = REPORTS_DIR / trading_date / "pre-market.md"
        if pre_market_path.exists():
            print(f"📖 Reading pre-market report from local: {pre_market_path}")
            with open(pre_market_path, "r", encoding="utf-8") as f:
                pre_market_content = f.read()
        else:
            print(f"⚠️ No pre-market report found for {trading_date} (Notion or local)")

    # Initialize components
    news_collector = NewsCollector()
    stock_collector = StockCollector()
    stock_analyzer = StockAnalyzer()
    report_generator = MarkdownReportGenerator()

    # Get news for context
    print("\n📰 Collecting news...")
    news_items = news_collector.collect_all()

    # Collect SEC and FDA (past 24 hours for post-market)
    sec_summary = _collect_sec_summary(hours_lookback=24, max_filings=15)
    fda_summary = _collect_fda_summary(days_lookback=1, max_results=8)
    regulatory_updates = _build_regulatory_updates(sec_summary, fda_summary)

    # Get market data
    print("📊 Fetching market data...")
    market_overview = stock_collector.get_market_overview()

    # Generate post-market review (comparing with pre-market predictions)
    print("🔍 Generating post-market review...")
    market_review = stock_analyzer.analyze_post_market_review(
        market_overview,
        pre_market_content=pre_market_content,
        news_items=news_items,
    )

    # Get watchlist with fundamental focus
    print("📋 Fetching watchlist...")
    all_stocks = stock_collector.collect_watchlist()
    watchlist_summary = stock_analyzer.generate_watchlist_fundamental_summary(
        all_stocks,
        news_items=news_items,
    )

    # Generate tomorrow outlook
    print("🔮 Generating tomorrow outlook...")
    tomorrow_outlook = stock_analyzer.generate_tomorrow_outlook(news_items)

    # Check for after-hours news (earnings, announcements)
    after_hours_news = ""
    earnings_keywords = ["earnings", "財報", "業績", "after hours", "盤後"]
    after_hours_items = [
        n for n in news_items
        if any(kw in n.title.lower() for kw in earnings_keywords)
    ]
    if after_hours_items:
        after_hours_news = "\n".join([
            f"- [{item.source}] {item.title}"
            for item in after_hours_items[:5]
        ])

    # Generate report
    print("\n📝 Generating report...")
    report = report_generator.generate_post_market_report(
        trading_date=trading_date,
        market_review=market_review,
        watchlist_summary=watchlist_summary,
        after_hours_news=after_hours_news,
        tomorrow_outlook=tomorrow_outlook,
        regulatory_updates=regulatory_updates,
    )

    # Upload to Notion (reuse publisher if already initialized)
    print("\n📤 Uploading to Notion...")
    if not notion_publisher:
        notion_publisher = NotionPublisher()
    # Convert trading_date (YYYY-MM-DD) to YYMMDD format for title
    title_date = datetime.strptime(trading_date, "%Y-%m-%d").strftime("%y%m%d")
    title = f"{title_date}_Post-market"

    # Extract stock tickers from report content for tags
    all_symbols = {s.symbol for s in all_stocks}
    stock_tags = extract_tickers_from_report(report, all_symbols)[:10]
    print(f"   Tags from report: {stock_tags}")

    page_url = notion_publisher.create_daily_page(
        title=title,
        content=report,
        report_type="post-market",
        date_str=trading_date,
        tags=stock_tags,
    )
    print(f"\n✅ Post-market report uploaded to Notion: {page_url}")

    return page_url


def generate_saturday_report(quick_mode: bool = False):
    """
    Generate Saturday industry analysis report (9am Taiwan = 1:00 UTC Saturday).

    This report uses the 6-prompt pipeline for deep industry analysis:
    1. Data classification and high-signal identification
    2. Paradigm shift analysis
    3. Technology frontier analysis
    4. Company moves analysis
    5. Final report generation

    Args:
        quick_mode: If True, use single-prompt quick analysis instead of full pipeline
    """
    print("\n" + "="*60)
    print("📊 Generating Saturday Industry Cognition Report")
    print("="*60)

    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    print(f"Time: {now.strftime('%Y-%m-%d %H:%M')} ({TIMEZONE})\n")

    # Initialize components
    intel_aggregator = IntelAggregator()
    industry_analyzer = IndustryAnalyzer()
    stock_collector = StockCollector()
    report_generator = MarkdownReportGenerator()

    # Collect intelligence from all sources (7 days lookback for weekly report)
    print("\n📥 Collecting intelligence from all sources...")
    intel_items = intel_aggregator.collect_all(
        days_lookback=7,
        include_news=True,
        include_sec=True,
        include_arxiv=True,
        include_trials=True,
        include_fda=True,
    )

    # Get summary stats
    stats = intel_aggregator.get_summary_stats(intel_items)
    print(f"\n📊 Intelligence Summary:")
    print(f"   Total items: {stats['total']}")
    print(f"   By type: {stats['by_source_type']}")
    print(f"   Top entities: {list(stats['top_entities'].keys())[:5]}")

    # Get market overview for context
    print("\n📈 Fetching market data...")
    market_overview = stock_collector.get_market_overview()

    week_market_summary = _format_weekly_market_summary(market_overview)

    # Run industry analysis
    if quick_mode:
        print("\n🤖 Running quick analysis (single prompt)...")
        industry_analysis = industry_analyzer.quick_analysis(intel_items[:100])
    else:
        print("\n🤖 Running full 6-step analysis pipeline...")
        analysis_result = industry_analyzer.analyze(intel_items[:150], run_full_pipeline=True)
        industry_analysis = analysis_result.final_report

    # Get watchlist for additional context
    print("\n📋 Fetching watchlist...")
    all_stocks = stock_collector.collect_watchlist()
    stock_analyzer = StockAnalyzer()
    watchlist_summary = stock_analyzer.generate_watchlist_summary(all_stocks)

    # Generate final report
    print("\n📝 Generating final report...")
    report = report_generator.generate_saturday_report(
        week_market_summary=week_market_summary,
        industry_analysis=industry_analysis,
        watchlist_summary=watchlist_summary,
    )

    # Upload to Notion
    print("\n📤 Uploading to Notion...")
    notion_publisher = NotionPublisher()
    date_str = now.strftime("%Y-%m-%d")
    title_date = now.strftime("%y%m%d")
    title = f"{title_date}_Saturday"

    # Extract tags from top entities and tickers
    top_tickers = list(stats['top_tickers'].keys())[:5]
    top_entities = [e for e in list(stats['top_entities'].keys())[:5] if len(e) <= 20]
    stock_tags = top_tickers + top_entities
    print(f"   Tags: {stock_tags[:10]}")

    page_url = notion_publisher.create_daily_page(
        title=title,
        content=report,
        report_type="saturday",
        date_str=date_str,
        tags=stock_tags[:10],
    )
    print(f"\n✅ Saturday report uploaded to Notion: {page_url}")

    return page_url


def generate_sunday_report():
    """Generate Sunday weekly outlook report (6pm Taiwan = 10:00 UTC Sunday)."""
    print("\n" + "="*60)
    print("🔮 Generating Sunday Weekly Outlook Report")
    print("="*60)

    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    print(f"Time: {now.strftime('%Y-%m-%d %H:%M')} ({TIMEZONE})\n")

    # Initialize components
    intel_aggregator = IntelAggregator()
    stock_collector = StockCollector()
    stock_analyzer = StockAnalyzer()
    report_generator = MarkdownReportGenerator()

    # Collect intelligence from all sources (7 days lookback for weekly report)
    print("📥 Collecting intelligence from all sources...")
    intel_items = intel_aggregator.collect_all(
        days_lookback=7,
        include_news=True,
        include_sec=True,
        include_arxiv=True,
        include_trials=True,
        include_fda=True,
    )

    # Get summary stats
    stats = intel_aggregator.get_summary_stats(intel_items)
    print(f"   Total items: {stats['total']}")
    print(f"   By type: {stats['by_source_type']}")

    # Extract news items for compatibility with existing analyzers
    news_items = [item for item in intel_items if item.source_type.value == "news"]
    print(f"   News items: {len(news_items)}")

    # Get market overview
    print("📊 Fetching market data...")
    market_overview = stock_collector.get_market_overview()

    # Generate weekly recap summary
    recap_lines = ["**本週指數表現：**", _format_weekly_market_summary(market_overview)]

    # Add weekly highlights from intel sources
    sec_items = [i for i in intel_items if i.source_type.value == "sec_filing"]
    fda_items = [i for i in intel_items if i.source_type.value == "regulatory"]
    arxiv_items = [i for i in intel_items if i.source_type.value == "research_paper"]

    if sec_items or fda_items or arxiv_items:
        recap_lines.append("\n**本週重要公告/研究：**")
        if sec_items:
            recap_lines.append(f"- SEC 公告: {len(sec_items)} 件")
        if fda_items:
            recap_lines.append(f"- FDA 動態: {len(fda_items)} 件")
        if arxiv_items:
            recap_lines.append(f"- AI/ML 論文: {len(arxiv_items)} 篇")

    weekly_recap = "\n".join(recap_lines)

    # Get watchlist
    print("📋 Fetching watchlist...")
    all_stocks = stock_collector.collect_watchlist()
    print(f"   Collected {len(all_stocks)} stocks")

    # Format intel highlights for outlook analysis
    intel_highlights = []
    for item in sec_items[:5]:
        intel_highlights.append(f"[SEC] {item.title}")
    for item in fda_items[:5]:
        intel_highlights.append(f"[FDA] {item.title}")
    for item in arxiv_items[:3]:
        intel_highlights.append(f"[Research] {item.title}")
    intel_context = "\n".join(intel_highlights) if intel_highlights else ""

    # Generate weekly outlook analysis
    print("🔮 Generating weekly outlook...")
    weekly_outlook = stock_analyzer.analyze_weekly_outlook(
        all_stocks,
        market_overview,
        news_items=news_items,
        intel_context=intel_context,
    )

    # Generate watchlist summary with fundamental focus
    watchlist_summary = stock_analyzer.generate_watchlist_fundamental_summary(
        all_stocks,
        news_items=news_items,
    )

    # Generate report
    print("\n📝 Generating report...")
    report = report_generator.generate_sunday_report(
        weekly_recap=weekly_recap,
        weekly_outlook=weekly_outlook,
        watchlist_summary=watchlist_summary,
    )

    # Upload to Notion
    print("\n📤 Uploading to Notion...")
    notion_publisher = NotionPublisher()
    date_str = now.strftime("%Y-%m-%d")
    title_date = now.strftime("%y%m%d")
    title = f"{title_date}_Sunday"

    # Extract stock tickers from report content for tags
    all_symbols = {s.symbol for s in all_stocks}
    stock_tags = extract_tickers_from_report(report, all_symbols)[:10]
    print(f"   Tags from report: {stock_tags}")

    page_url = notion_publisher.create_daily_page(
        title=title,
        content=report,
        report_type="sunday",
        date_str=date_str,
        tags=stock_tags,
    )
    print(f"\n✅ Sunday report uploaded to Notion: {page_url}")

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
            analyzer = StockAnalyzer()
            print("   ✅ StockAnalyzer initialized")

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
        choices=["pre-market", "post-market", "saturday", "sunday", "test"],
        help="Report type to generate",
    )

    args = parser.parse_args()

    # Check API keys for non-test commands
    if args.command != "test" and not check_api_keys():
        sys.exit(1)

    try:
        if args.command == "pre-market":
            generate_pre_market_report()

        elif args.command == "post-market":
            generate_post_market_report()

        elif args.command == "saturday":
            generate_saturday_report()

        elif args.command == "sunday":
            generate_sunday_report()

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
