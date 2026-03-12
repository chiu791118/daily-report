"""
Stock Analyzer Module
Uses Gemini AI to analyze stocks with integrated news and video insights.
"""
from google import genai
from google.genai import types


from src.config.settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_TEMPERATURE,
    GEMINI_MAX_OUTPUT_TOKENS,
)
from src.collectors.stocks import StockData, MarketOverview
from src.collectors.news import NewsItem


class StockAnalyzer:
    """Analyzes stocks using technical data and AI insights."""

    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not set in environment")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model = GEMINI_MODEL
        self.generation_config = types.GenerateContentConfig(
            temperature=GEMINI_TEMPERATURE,
            max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
        )

    def analyze_stock(
        self,
        stock: StockData,
        related_news: list[NewsItem] = None,
        video_mentions: list[dict] = None,
    ) -> dict:
        """Analyze a single stock with integrated context."""

        # Format stock data
        stock_info = self._format_stock_data(stock)

        # Format related news
        news_context = ""
        if related_news:
            news_context = "\n## 相關新聞\n" + "\n".join(
                f"- [{n.source}] {n.title}" for n in related_news[:5]
            )

        # Format video mentions
        video_context = ""
        if video_mentions:
            video_context = "\n## YouTuber 觀點\n" + "\n".join(
                f"- [{v['channel']}]: {v['opinion']}" for v in video_mentions[:5]
            )

        prompt = f"""你是一位專業的股票分析師。請分析以下股票並提供投資建議。

## 股票資料

{stock_info}
{news_context}
{video_context}

## 請提供以下分析（使用繁體中文回答）：

### 1. 技術面分析
- 目前趨勢評估
- 支撐與壓力位分析
- 成交量訊號解讀
- RSI 和移動平均線分析

### 2. 基本面簡評
根據本益比和市值，評估目前估值是否合理。

### 3. 近期催化劑
可能影響股價的近期事件或因素。

### 4. 風險評估
- 主要風險因素
- 風險程度（低/中/高）

### 5. 操作建議
- 短期（1-2 週）：觀望 / 買入 / 賣出
- 中期（1-3 月）：看漲 / 中性 / 看跌
- 關鍵價位提醒

### 6. 總結
一句話總結對這支股票的看法。

請以結構化的格式回答。"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self.generation_config,
            )

            return {
                "symbol": stock.symbol,
                "name": stock.name,
                "current_price": stock.current_price,
                "change_percent": stock.change_percent,
                "analysis": response.text,
                "trend": stock.trend,
                "volume_signal": stock.volume_signal,
            }

        except Exception as e:
            print(f"Error analyzing {stock.symbol}: {e}")
            return {
                "symbol": stock.symbol,
                "name": stock.name,
                "current_price": stock.current_price,
                "change_percent": stock.change_percent,
                "analysis": f"分析時發生錯誤: {e}",
                "trend": stock.trend,
                "volume_signal": stock.volume_signal,
            }

    def _format_stock_data(self, stock: StockData) -> str:
        """Format stock data for analysis prompt."""
        lines = [
            f"**{stock.symbol} - {stock.name}**",
            f"- 類別: {stock.category}",
            f"- 備註: {stock.notes}" if stock.notes else "",
            "",
            "**價格資訊**",
            f"- 現價: ${stock.current_price:,.2f}",
            f"- 前收盤: ${stock.previous_close:,.2f}",
            f"- 漲跌幅: {stock.change_percent:+.2f}%",
            f"- 52 週高點: ${stock.high_52w:,.2f}",
            f"- 52 週低點: ${stock.low_52w:,.2f}",
            "",
            "**成交量**",
            f"- 今日成交量: {stock.volume:,}",
            f"- 平均成交量: {stock.avg_volume:,}",
            f"- 成交量比率: {stock.volume_ratio:.2f}x",
            "",
            "**技術指標**",
            f"- 20日均線: ${stock.sma_20:,.2f}" if stock.sma_20 else "- 20日均線: N/A",
            f"- 50日均線: ${stock.sma_50:,.2f}" if stock.sma_50 else "- 50日均線: N/A",
            f"- 200日均線: ${stock.sma_200:,.2f}" if stock.sma_200 else "- 200日均線: N/A",
            f"- RSI(14): {stock.rsi_14:.1f}" if stock.rsi_14 else "- RSI(14): N/A",
            f"- 趨勢判斷: {stock.trend}",
            "",
            "**近期表現**",
            f"- 1週: {stock.change_1w:+.2f}%" if stock.change_1w else "- 1週: N/A",
            f"- 1月: {stock.change_1m:+.2f}%" if stock.change_1m else "- 1月: N/A",
            f"- 3月: {stock.change_3m:+.2f}%" if stock.change_3m else "- 3月: N/A",
            "",
            "**估值**",
            f"- 市值: ${stock.market_cap/1e9:.2f}B" if stock.market_cap else "- 市值: N/A",
            f"- 本益比: {stock.pe_ratio:.1f}" if stock.pe_ratio else "- 本益比: N/A",
        ]

        if stock.support_levels:
            lines.append(f"- 支撐位: {', '.join(f'${p}' for p in stock.support_levels)}")
        if stock.resistance_levels:
            lines.append(f"- 壓力位: {', '.join(f'${p}' for p in stock.resistance_levels)}")

        return "\n".join(line for line in lines if line)

    def analyze_market_overview(
        self,
        overview: MarketOverview,
        news_items: list[NewsItem] = None,
        is_monday: bool = False,
    ) -> str:
        """Generate market overview analysis based on today's news."""
        from datetime import datetime
        import pytz

        data = []

        if overview.sp500:
            data.append(f"- S&P 500: {overview.sp500.current_price:,.2f} ({overview.sp500.change_percent:+.2f}%)")
        if overview.nasdaq:
            data.append(f"- NASDAQ: {overview.nasdaq.current_price:,.2f} ({overview.nasdaq.change_percent:+.2f}%)")
        if overview.dow:
            data.append(f"- Dow Jones: {overview.dow.current_price:,.2f} ({overview.dow.change_percent:+.2f}%)")
        if overview.vix:
            data.append(f"- VIX 恐慌指數: {overview.vix:.2f} ({overview.vix_change:+.2f}%)")

        data_text = "\n".join(data)

        # 格式化今日新聞供分析參考
        news_context = ""
        if news_items:
            by_source = {}
            for item in news_items:
                if item.source not in by_source:
                    by_source[item.source] = []
                by_source[item.source].append(item)

            news_lines = []
            for source, items in by_source.items():
                news_lines.append(f"**{source}**")
                for item in items[:10]:
                    tickers = f" [{', '.join(item.related_tickers)}]" if item.related_tickers else ""
                    news_lines.append(f"- {item.title}{tickers}")
                news_lines.append("")
            news_context = "\n".join(news_lines)

        # 週一才加入本週關注焦點
        weekly_focus_section = ""
        if is_monday:
            weekly_focus_section = """
### 5. 本週關注焦點

**重要經濟數據發布：**
- 列出本週將公布的重要經濟數據（日期、時間、預期值）
- 哪些數據最可能影響市場走向

**財報發布：**
- 本週重要公司財報時間表
- 哪些財報最值得關注，為什麼

**其他重要事件：**
- 央行官員發言、政策會議
- 地緣政治事件、貿易談判等
"""

        prompt = f"""**如果你必須加入免責聲明，請全部集中放在回覆的最前面，之後的分析內容不要再出現任何免責措辭。**

你是一位頂尖的投資顧問，具備總體經濟、產業分析、個股研究、ETF、指數、房地產、衍生性金融商品的專業知識。

**【最重要原則】以下所有分析必須 100% 基於「今日新聞」的具體內容進行推導。禁止使用「假設」、「可能」等空泛措辭。如果新聞中沒有提及某項內容，就不要編造。每個觀點都必須能追溯到具體的新聞事件。**

## 今日市場數據
{data_text}
市場情緒判讀: {overview.market_sentiment}

## 今日新聞（這是你唯一的分析依據）
{news_context if news_context else "無新聞資料"}

---

## 請提供以下深度分析（1000-1500 字）：

### 1. 今日市場解讀（基於新聞）

**美股指數表現與驅動因素：**
- 根據今日新聞，三大指數表現背後的具體原因是什麼？
- 指數間的相對強弱（例：NASDAQ vs Dow）反映了什麼資金動向？
- 引用具體新聞事件來解釋市場走勢

**全球市場連動（如果新聞有涵蓋）：**
- 今日新聞中提到的歐洲、亞洲市場動態
- 全球市場間的連動或背離現象
- 匯率變動（美元、歐元、日圓）及其影響

### 2. 總經與政策環境（基於今日新聞）

**今日新聞中的總經相關資訊：**
- 新聞中提到的經濟數據（CPI、PPI、就業、GDP 等）及其意涵
- 聯準會或其他央行的最新動態、官員發言
- 這些資訊對利率預期和市場的影響

**財政與政治因素（基於今日新聞）：**
- 新聞中提到的政策變動、政治事件
- 地緣政治風險（貿易、制裁、軍事衝突等）
- 這些因素對市場的具體影響

### 3. 市場情緒與風險評估

**VIX 與市場氛圍：**
- VIX {overview.vix:.1f} 代表什麼樣的市場氛圍？（恐慌/謹慎/樂觀/過度樂觀）
- 與歷史水平相比處於什麼位置？
- 結合今日新聞事件，這個 VIX 水平合理嗎？

**風險環境綜合評估：**
- 根據今日新聞，當前主要風險因素有哪些？
- 避險資產（黃金、美債、日圓）的表現
- 整體風險水平判斷

### 4. 資金流向與配置建議（基於今日新聞推導）

**板塊動態（根據新聞推導）：**
- 今日新聞利好哪些板塊？為什麼？
- 今日新聞利空哪些板塊？為什麼？
- 資金可能的流向判斷

**跨資產觀點：**
- 股票、債券、商品、現金的相對吸引力
- 今日新聞對這些資產類別的影響

### 操作建議

**整體倉位：**
- 建議股票倉位：___%
- 理由：基於今日新聞和市場數據的綜合判斷

**具體操作建議（必須給出明確標的）：**
- 買入：具體標的代碼、建議價位、停損價位
- 賣出/減碼：具體標的代碼、理由
- 觀望：哪些標的需要等待什麼訊號
{weekly_focus_section}
**重要提醒：所有分析必須基於上方提供的今日新聞，不要編造或假設新聞中沒有的資訊。如果某項內容新聞中沒有涵蓋，請直接說明「今日新聞未涵蓋此項」。**"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=6000,
                ),
            )
            return response.text
        except Exception as e:
            return f"無法生成市場概況: {e}"

    def generate_watchlist_summary(self, stocks: list[StockData]) -> str:
        """Generate a summary table for the watchlist."""
        if not stocks:
            return "沒有觀察清單中的股票數據。"

        lines = ["## 📊 觀察清單概覽\n"]
        lines.append("| 代號 | 名稱 | 現價 | 漲跌幅 | 趨勢 | RSI | 成交量 |")
        lines.append("|------|------|------|--------|------|-----|--------|")

        for stock in stocks:
            rsi = f"{stock.rsi_14:.0f}" if stock.rsi_14 else "N/A"
            lines.append(
                f"| {stock.symbol} | {stock.name[:15]} | "
                f"${stock.current_price:,.2f} | "
                f"{stock.change_percent:+.2f}% | "
                f"{stock.trend} | {rsi} | "
                f"{stock.volume_signal} |"
            )

        # Add notable movers
        movers = sorted(stocks, key=lambda x: abs(x.change_percent), reverse=True)[:3]
        if movers:
            lines.append("\n### 🔥 今日顯著變動")
            for stock in movers:
                direction = "📈" if stock.change_percent > 0 else "📉"
                lines.append(
                    f"- {direction} **{stock.symbol}** ({stock.change_percent:+.2f}%): "
                    f"{stock.trend}"
                )

        return "\n".join(lines)

    def generate_filtered_watchlist_summary(
        self,
        filtered_stocks: dict,
        news_items: list = None,
    ) -> str:
        """Generate summary for filtered/relevant stocks only."""
        lines = []

        # News-related stocks
        if filtered_stocks.get("news_related"):
            lines.append("## 📰 新聞相關標的\n")
            lines.append("以下股票在今日新聞中被提及：\n")
            lines.append("| 代號 | 名稱 | 現價 | 漲跌幅 | 趨勢 |")
            lines.append("|------|------|------|--------|------|")

            for stock in sorted(filtered_stocks["news_related"], key=lambda x: abs(x.change_percent), reverse=True):
                lines.append(
                    f"| **{stock.symbol}** | {stock.name[:20]} | "
                    f"${stock.current_price:,.2f} | "
                    f"{stock.change_percent:+.2f}% | "
                    f"{stock.trend} |"
                )
            lines.append("")

        # Significant movers
        if filtered_stocks.get("significant_movers"):
            lines.append("## 🔥 顯著變動標的\n")
            lines.append("以下股票今日漲跌幅超過 3%：\n")

            for stock in sorted(filtered_stocks["significant_movers"], key=lambda x: abs(x.change_percent), reverse=True):
                direction = "📈" if stock.change_percent > 0 else "📉"
                rsi_note = ""
                if stock.rsi_14:
                    if stock.rsi_14 > 70:
                        rsi_note = " (RSI 超買)"
                    elif stock.rsi_14 < 30:
                        rsi_note = " (RSI 超賣)"

                lines.append(
                    f"- {direction} **{stock.symbol}** {stock.change_percent:+.2f}% "
                    f"(${stock.current_price:,.2f}){rsi_note}"
                )
            lines.append("")

        # Priority watchlist (brief)
        if filtered_stocks.get("priority"):
            lines.append("## ⭐ 優先觀察清單\n")
            priority_data = []
            for stock in filtered_stocks["priority"]:
                direction = "🟢" if stock.change_percent > 0 else "🔴" if stock.change_percent < 0 else "⚪"
                priority_data.append(f"{direction} {stock.symbol} {stock.change_percent:+.1f}%")

            # Display in a compact format
            lines.append(" | ".join(priority_data))
            lines.append("")

        if not any([filtered_stocks.get("news_related"), filtered_stocks.get("significant_movers"), filtered_stocks.get("priority")]):
            lines.append("今日沒有特別需要關注的標的。")

        return "\n".join(lines)

    def analyze_post_market_review(
        self,
        overview: MarketOverview,
        pre_market_content: str,
        news_items: list[NewsItem] = None,
    ) -> str:
        """Generate post-market review comparing predictions vs actual results."""
        data = []

        if overview.sp500:
            data.append(f"- S&P 500: {overview.sp500.current_price:,.2f} ({overview.sp500.change_percent:+.2f}%)")
        if overview.nasdaq:
            data.append(f"- NASDAQ: {overview.nasdaq.current_price:,.2f} ({overview.nasdaq.change_percent:+.2f}%)")
        if overview.dow:
            data.append(f"- Dow Jones: {overview.dow.current_price:,.2f} ({overview.dow.change_percent:+.2f}%)")
        if overview.vix:
            data.append(f"- VIX: {overview.vix:.2f} ({overview.vix_change:+.2f}%)")

        data_text = "\n".join(data)

        # Format news for context
        news_context = ""
        if news_items:
            news_lines = []
            for item in news_items[:15]:
                news_lines.append(f"- [{item.source}] {item.title}")
            news_context = "\n".join(news_lines)

        prompt = f"""你是一位專業的投資顧問，正在進行每日收盤後覆盤。

## 今日盤前報告內容（預測）
{pre_market_content[:8000] if pre_market_content else "無盤前報告"}

## 今日實際收盤數據
{data_text}

## 今日相關新聞
{news_context if news_context else "無新聞"}

---

## 請提供收盤後覆盤分析（800-1200 字）：

### 1. 今日市場實際表現

**三大指數收盤總結：**
- S&P 500、NASDAQ、Dow Jones 今日實際漲跌幅
- 盤中走勢特徵（開高走低？開低走高？全日震盪？）
- 收盤價相對於盤中高低點的位置

**預期 vs 現實對比：**
- 盤前報告的主要預測是什麼？
- 實際結果與預測相符還是背離？
- 如果背離，原因是什麼？（新的消息、市場情緒變化、技術面因素）

**今日實際驅動因素：**
- 根據收盤後回顧，今天市場真正的驅動因素是什麼？
- 哪些新聞/事件對市場影響最大？

### 2. 關鍵觀察與學習

**盤前預測的準確度：**
- 哪些預測是對的？為什麼？
- 哪些預測是錯的？為什麼？
- 這次覆盤有什麼可以學習的地方？

**市場情緒變化：**
- VIX 的變化代表什麼？
- 成交量相對於平均的意義
- 盤中情緒的變化（是否有恐慌或貪婪的跡象）

### 3. 對後續的影響

- 今日的走勢對明天有什麼暗示？
- 是否形成新的支撐或壓力？
- 需要調整的觀點或策略

請以覆盤的角度回答，重點是「發生了什麼」和「學到什麼」，而非預測。"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=4000,
                ),
            )
            return response.text
        except Exception as e:
            return f"無法生成覆盤分析: {e}"

    def generate_watchlist_fundamental_summary(
        self,
        stocks: list[StockData],
        news_items: list[NewsItem] = None,
    ) -> str:
        """Generate watchlist summary with fundamental focus."""
        if not stocks:
            return "沒有觀察清單中的股票數據。"

        # Sort by absolute change
        sorted_stocks = sorted(stocks, key=lambda x: abs(x.change_percent), reverse=True)

        lines = []

        # Performance table
        lines.append("### 今日表現總覽\n")
        lines.append("| 代號 | 名稱 | 收盤價 | 漲跌幅 | 市值 | 本益比 |")
        lines.append("|------|------|--------|--------|------|--------|")

        for stock in sorted_stocks[:20]:
            pe = f"{stock.pe_ratio:.1f}" if stock.pe_ratio else "N/A"
            mcap = f"${stock.market_cap/1e9:.0f}B" if stock.market_cap else "N/A"
            lines.append(
                f"| {stock.symbol} | {stock.name[:15]} | "
                f"${stock.current_price:,.2f} | "
                f"{stock.change_percent:+.2f}% | "
                f"{mcap} | {pe} |"
            )

        # Significant movers with context
        movers = [s for s in sorted_stocks if abs(s.change_percent) >= 3.0]
        if movers:
            lines.append("\n### 顯著變動標的（基本面解讀）\n")
            for stock in movers[:8]:
                direction = "📈" if stock.change_percent > 0 else "📉"
                pe_note = ""
                if stock.pe_ratio:
                    if stock.pe_ratio > 50:
                        pe_note = "（高估值）"
                    elif stock.pe_ratio < 15:
                        pe_note = "（低估值）"

                # Find related news
                related_news = ""
                if news_items:
                    for news in news_items:
                        if stock.symbol in news.related_tickers:
                            related_news = f"\n  - 相關新聞: {news.title[:60]}..."
                            break

                lines.append(
                    f"- {direction} **{stock.symbol}** {stock.change_percent:+.2f}% "
                    f"(${stock.current_price:,.2f}){pe_note}{related_news}"
                )

        return "\n".join(lines)

    def generate_tomorrow_outlook(self, news_items: list[NewsItem] = None) -> str:
        """Generate tomorrow's outlook with key events."""
        if not news_items:
            return "明日無特別需要關注的事件。"

        # Extract any forward-looking news
        news_text = "\n".join([f"- {item.title}" for item in news_items[:10]])

        prompt = f"""根據以下今日新聞，提取明日需要關注的事件：

{news_text}

請簡短列出（100-200 字）：
1. 明日將公布的重要經濟數據（如有提及）
2. 明日將發布的重要財報（如有提及）
3. 其他需要關注的事件或風險

如果新聞中沒有提及明日事件，請說明「今日新聞未提及明日特定事件」。
不要編造新聞中沒有的內容。"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=500,
                ),
            )
            return response.text
        except Exception as e:
            return f"無法生成明日展望: {e}"

    def analyze_industry_report(
        self,
        stocks: list[StockData],
        overview: MarketOverview,
        news_items: list[NewsItem] = None,
    ) -> str:
        """Generate Saturday industry analysis report with company profiles."""
        # Format market overview
        market_data = []
        if overview.sp500:
            market_data.append(f"- S&P 500: {overview.sp500.current_price:,.2f} (本週 {overview.sp500.change_1w:+.2f}%)" if overview.sp500.change_1w else f"- S&P 500: {overview.sp500.current_price:,.2f}")
        if overview.nasdaq:
            market_data.append(f"- NASDAQ: {overview.nasdaq.current_price:,.2f} (本週 {overview.nasdaq.change_1w:+.2f}%)" if overview.nasdaq.change_1w else f"- NASDAQ: {overview.nasdaq.current_price:,.2f}")
        if overview.dow:
            market_data.append(f"- Dow Jones: {overview.dow.current_price:,.2f} (本週 {overview.dow.change_1w:+.2f}%)" if overview.dow.change_1w else f"- Dow Jones: {overview.dow.current_price:,.2f}")
        market_summary = "\n".join(market_data)

        # Group stocks by category and calculate sector performance
        sector_performance = {}
        for stock in stocks:
            category = stock.category or "其他"
            if category not in sector_performance:
                sector_performance[category] = []
            sector_performance[category].append(stock)

        # Format sector data
        sector_lines = []
        for sector, sector_stocks in sorted(sector_performance.items()):
            avg_change = sum(s.change_1w or s.change_percent for s in sector_stocks) / len(sector_stocks)
            top_stock = max(sector_stocks, key=lambda x: x.change_1w or x.change_percent)
            sector_lines.append(f"- {sector}: 平均 {avg_change:+.2f}% (代表: {top_stock.symbol} {top_stock.change_1w or top_stock.change_percent:+.2f}%)")
        sector_summary = "\n".join(sector_lines)

        # Format top stocks for company profiles
        top_movers = sorted(stocks, key=lambda x: abs(x.change_1w or x.change_percent), reverse=True)[:10]
        stock_profiles = []
        for stock in top_movers:
            pe = f"本益比: {stock.pe_ratio:.1f}" if stock.pe_ratio else "本益比: N/A"
            mcap = f"市值: ${stock.market_cap/1e9:.1f}B" if stock.market_cap else "市值: N/A"
            stock_profiles.append(f"- {stock.symbol} ({stock.name}): {pe}, {mcap}, 本週 {stock.change_1w or stock.change_percent:+.2f}%")
        stocks_summary = "\n".join(stock_profiles)

        # Format news context
        news_context = ""
        if news_items:
            news_lines = [f"- [{n.source}] {n.title}" for n in news_items[:20]]
            news_context = "\n".join(news_lines)

        prompt = f"""你是一位專業的投資研究分析師，正在撰寫週末產業分析報告。

## 本週市場數據
{market_summary}

## 板塊表現概覽
{sector_summary}

## 觀察清單中的代表性股票
{stocks_summary}

## 本週相關新聞
{news_context if news_context else "無新聞資料"}

---

## 請提供以下產業分析報告（1500-2000 字）：

### 1. 本週市場概覽（約 300 字）

**指數表現總結：**
- 三大指數本週表現與走勢特徵
- 板塊輪動分析（哪些板塊領漲/領跌）
- 成交量與市場情緒變化

### 2. 產業深度分析（800-1000 字）

根據本週板塊表現，選擇 2-3 個最值得關注的產業進行深度分析：

**產業一：[產業名稱]**
- 產業現狀與市場規模
- 本週表現驅動因素
- 主要參與者及競爭格局
- 產業發展趨勢與投資邏輯
- 需要關注的風險因素

**產業二：[產業名稱]**
（相同結構）

**產業三：[產業名稱]**（如適用）
（相同結構）

### 3. 公司商業模式介紹（600-800 字）

從上述產業中選擇 3-5 家代表性公司，深入介紹：

**[公司名稱] (代碼)**
- **商業模式**：公司如何賺錢？主要收入來源？
- **競爭優勢**：護城河是什麼？（品牌、技術、規模、網絡效應等）
- **市場地位**：在行業中的位置？市佔率？
- **近期發展**：最新動態、財報重點、策略變化
- **關鍵指標**：投資者應關注的 KPI

### 4. 投資機會與風險（200-300 字）

**潛在機會：**
- 基於產業分析，哪些投資機會值得關注？
- 具體標的建議（如有）

**風險提醒：**
- 產業面臨的主要風險
- 需要監控的關鍵指標

請以專業但易懂的方式撰寫，幫助投資者理解這些產業和公司。"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.4,
                    max_output_tokens=6000,
                ),
            )
            return response.text
        except Exception as e:
            return f"無法生成產業分析報告: {e}"

    def analyze_weekly_outlook(
        self,
        stocks: list[StockData],
        overview: MarketOverview,
        news_items: list[NewsItem] = None,
        intel_context: str = "",
    ) -> str:
        """Generate Sunday weekly outlook report with next week preview."""
        # Format market overview
        market_data = []
        if overview.sp500:
            weekly_change = f" (本週 {overview.sp500.change_1w:+.2f}%)" if overview.sp500.change_1w else ""
            market_data.append(f"- S&P 500: {overview.sp500.current_price:,.2f}{weekly_change}")
        if overview.nasdaq:
            weekly_change = f" (本週 {overview.nasdaq.change_1w:+.2f}%)" if overview.nasdaq.change_1w else ""
            market_data.append(f"- NASDAQ: {overview.nasdaq.current_price:,.2f}{weekly_change}")
        if overview.dow:
            weekly_change = f" (本週 {overview.dow.change_1w:+.2f}%)" if overview.dow.change_1w else ""
            market_data.append(f"- Dow Jones: {overview.dow.current_price:,.2f}{weekly_change}")
        if overview.vix:
            market_data.append(f"- VIX: {overview.vix:.2f}")
        market_summary = "\n".join(market_data)

        # Format top performers and losers
        sorted_by_week = sorted(stocks, key=lambda x: x.change_1w or x.change_percent, reverse=True)
        top_winners = sorted_by_week[:5]
        top_losers = sorted_by_week[-5:]

        winners_text = "\n".join([f"- {s.symbol}: {s.change_1w or s.change_percent:+.2f}%" for s in top_winners])
        losers_text = "\n".join([f"- {s.symbol}: {s.change_1w or s.change_percent:+.2f}%" for s in top_losers])

        # Technical levels for major indices
        tech_levels = []
        if overview.sp500:
            if overview.sp500.sma_20:
                tech_levels.append(f"- S&P 500 20日均線: {overview.sp500.sma_20:,.2f}")
            if overview.sp500.sma_50:
                tech_levels.append(f"- S&P 500 50日均線: {overview.sp500.sma_50:,.2f}")
        tech_summary = "\n".join(tech_levels) if tech_levels else "技術指標資料不足"

        # Format news context
        news_context = ""
        if news_items:
            news_lines = [f"- [{n.source}] {n.title}" for n in news_items[:25]]
            news_context = "\n".join(news_lines)

        prompt = f"""你是一位專業的投資顧問，正在撰寫週末展望報告，幫助投資者為下週做好準備。

## 本週市場收盤數據
{market_summary}

## 本週最大贏家
{winners_text}

## 本週最大輸家
{losers_text}

## 技術面數據
{tech_summary}

## 本週相關新聞
{news_context if news_context else "無新聞資料"}

## 本週重要公告與研究
{intel_context if intel_context else "無額外資料"}

---

## 請提供以下週末展望報告（1500-2000 字）：

### 1. 本週回顧（400-500 字）

**每日市場走勢：**
- 週一至週五的市場表現（根據新聞推測）
- 盤中波動特徵與收盤位置
- 本週的關鍵轉折點

**本週大事記：**
- 影響市場的重要事件（政策、數據、財報等）
- 這些事件如何影響了市場走勢

**本週贏家與輸家：**
- 表現最好/最差的股票或板塊
- 背後的原因分析

### 2. 下週關注焦點（500-700 字）

**重要經濟數據日曆：**
（請列出下週可能發布的重要經濟數據）
- 週一：
- 週二：
- 週三：
- 週四：
- 週五：

**重要財報發布：**
- 列出下週將發布財報的重要公司
- 市場對這些財報的預期
- 需要關注的關鍵指標

**Fed 與央行動態：**
- 下週是否有 FOMC 會議或官員發言
- 對市場可能的影響

**其他重要事件：**
- 地緣政治、貿易、政策等

### 3. 技術面觀察（300 字）

**指數技術分析：**
- S&P 500 關鍵支撐與壓力位
- NASDAQ 技術面狀態
- 需要突破或守住的關鍵價位

**技術面訊號：**
- 目前的技術面偏多或偏空
- 需要關注的技術形態

### 4. 下週操作策略建議（300-400 字）

**整體策略：**
- 建議的倉位水平
- 進攻型 vs 防守型配置

**板塊配置建議：**
- 建議增持的板塊及原因
- 建議減持的板塊及原因

**具體觀察標的：**
- 下週值得關注的股票
- 設定的觀察價位

**風險管理提醒：**
- 下週可能的風險事件
- 停損與獲利了結建議

請以實用、可操作的角度撰寫，幫助投資者規劃下週的交易策略。"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.4,
                    max_output_tokens=6000,
                ),
            )
            return response.text
        except Exception as e:
            return f"無法生成週末展望報告: {e}"

    def generate_global_snapshot(
        self,
        overview: MarketOverview,
        news_items: list[NewsItem] = None,
    ) -> str:
        """
        Generate a concise global market snapshot with interpretations.
        Similar to Maggie's Global View format.
        """
        # Format market data
        market_lines = []
        if overview.sp500:
            market_lines.append(f"S&P 500: {overview.sp500.current_price:,.2f} | {overview.sp500.change_percent:+.2f}%")
        if overview.nasdaq:
            market_lines.append(f"NASDAQ: {overview.nasdaq.current_price:,.2f} | {overview.nasdaq.change_percent:+.2f}%")
        if overview.dow:
            market_lines.append(f"Dow Jones: {overview.dow.current_price:,.2f} | {overview.dow.change_percent:+.2f}%")

        market_data = "\n".join(market_lines)

        # Format news headlines
        news_context = ""
        if news_items:
            news_lines = [f"- {n.title}" for n in news_items[:20]]
            news_context = "\n".join(news_lines)

        prompt = f"""你是一位全球財經早報編輯，風格簡潔有力。

## 隔夜市場數據
{market_data}

## 今日主要新聞標題
{news_context if news_context else "無新聞"}

---

請生成「隔夜核心行情」快覽，格式如下：

### 隔夜核心行情

對每個指數/資產，用一行呈現：
● [資產名稱]: [價格] [漲跌幅] ([一句話市場解讀])

要求：
1. 括號內的解讀要精準點出漲跌原因（如「科技股拋售」「Fed鴿派預期」「避險需求」）
2. 只用 4-6 個 bullet points
3. 如有重要的其他資產（如黃金、原油、比特幣、美元指數）根據新聞判斷是否納入
4. 語言簡潔，不要廢話

### 今日關鍵主題

用三行總結今日最重要的三個主題：
🏛️ **宏觀**: [一句話，10-15字]
⚡ **科技**: [一句話，10-15字]
🏢 **產業**: [一句話，10-15字]

使用繁體中文。"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=1000,
                ),
            )
            return response.text
        except Exception as e:
            return f"無法生成全球快覽: {e}"

    def categorize_news(
        self,
        news_items: list[NewsItem],
    ) -> dict:
        """
        Categorize news into three categories:
        1. 宏觀與政策 (Macro & Policy)
        2. 科技與地緣 (Tech & Geopolitics)
        3. 巨頭與產業 (Market Movers)

        Returns dict with 'macro', 'tech', 'industry' keys.
        """
        if not news_items:
            return {'macro': '', 'tech': '', 'industry': ''}

        # Format news
        news_text = "\n".join([
            f"- [{n.source}] {n.title}"
            for n in news_items[:40]
        ])

        prompt = f"""你是一位全球財經早報編輯。請將以下新聞分類並重新整理。

## 原始新聞列表
{news_text}

---

請將新聞分為三類，每類選出 2-4 條最重要的新聞：

## 分類標準

**宏觀與政策 (Macro & Policy)**：
- 央行政策（Fed、ECB、BOJ等）
- 政府財政政策
- 國際貿易協定
- 地緣政治衝突
- 重大政治事件

**科技與地緣 (Tech & Geopolitics)**：
- AI/科技公司動態
- 晶片/半導體
- 科技監管
- 中美科技競爭
- 科技人才流動

**巨頭與產業 (Market Movers)**：
- 個別公司財報/業績
- 併購/重組
- 商品價格（油、金、銅等）
- 產業趨勢
- 中國市場動態

---

## 輸出格式

對每條新聞，請用以下格式：

◆ **[簡短標題，8-12字]**
[2-3句說明，包含市場影響]

要求：
1. 每類最多 4 條
2. 標題要精煉，不要照抄原標題
3. 說明要包含「所以呢？」（市場影響）
4. 使用繁體中文
5. 如果某類沒有相關新聞，輸出「今日無重大相關新聞。」

請依照以下 JSON 格式輸出：
```json
{{
  "macro": "◆ **標題1**\\n說明...\\n\\n◆ **標題2**\\n說明...",
  "tech": "◆ **標題1**\\n說明...\\n\\n◆ **標題2**\\n說明...",
  "industry": "◆ **標題1**\\n說明...\\n\\n◆ **標題2**\\n說明..."
}}
```"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=2500,
                ),
            )

            # Parse JSON response
            import json
            import re

            text = response.text
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                result = json.loads(json_match.group())
                return {
                    'macro': result.get('macro', ''),
                    'tech': result.get('tech', ''),
                    'industry': result.get('industry', ''),
                }
            else:
                # Fallback: return raw text split
                return {'macro': text, 'tech': '', 'industry': ''}

        except Exception as e:
            return {'macro': f'分類錯誤: {e}', 'tech': '', 'industry': ''}

    def extract_hashtags(
        self,
        news_items: list[NewsItem],
        market_overview: MarketOverview = None,
    ) -> list[str]:
        """
        Extract key hashtags/themes from today's news.
        Returns list of 4-6 hashtag strings (without # symbol).
        """
        if not news_items:
            return []

        # Format news
        news_text = "\n".join([n.title for n in news_items[:30]])

        prompt = f"""根據以下今日新聞標題，提取 4-6 個關鍵主題標籤。

## 新聞標題
{news_text}

---

## 要求
1. 每個標籤 2-4 個中文字
2. 要能一眼概括當日主題
3. 優先選擇：公司名、政策名、事件名、趨勢名
4. 不要太泛（如「股市」「科技」）

## 輸出格式
只輸出標籤，用逗號分隔，不要加 # 符號。

範例輸出：
Fed降息, AI監管, 特斯拉財報, 黃金新高, 中概股暴跌"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=200,
                ),
            )

            # Parse comma-separated tags
            tags = [tag.strip() for tag in response.text.split(',')]
            return [tag for tag in tags if tag and len(tag) <= 10][:6]

        except Exception as e:
            return []


def main():
    """Test the stock analyzer."""
    from src.collectors.stocks import StockCollector

    try:
        collector = StockCollector()

        # Get market overview
        print("\n=== Market Overview Analysis ===\n")
        overview = collector.get_market_overview()

        analyzer = StockAnalyzer()
        market_analysis = analyzer.analyze_market_overview(overview)
        print(market_analysis)

        # Get watchlist
        print("\n=== Watchlist Summary ===\n")
        stocks = collector.collect_watchlist()
        summary = analyzer.generate_watchlist_summary(stocks)
        print(summary)

        # Analyze first stock in detail
        if stocks:
            print("\n=== Detailed Analysis ===\n")
            analysis = analyzer.analyze_stock(stocks[0])
            print(analysis["analysis"])

    except ValueError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
