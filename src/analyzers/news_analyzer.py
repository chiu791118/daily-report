"""
News Analyzer Module
Uses Gemini AI to analyze and summarize financial news with stock-specific insights.
"""
from google import genai
from google.genai import types
from typing import Optional


from src.config.settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_TEMPERATURE,
    GEMINI_MAX_OUTPUT_TOKENS,
)
from src.collectors.news import NewsItem


class NewsAnalyzer:
    """Analyzes financial news using Gemini AI."""

    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not set in environment")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model = GEMINI_MODEL
        self.generation_config = types.GenerateContentConfig(
            temperature=GEMINI_TEMPERATURE,
            max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
        )

    def analyze_news_batch(self, news_items: list[NewsItem]) -> dict:
        """Analyze a batch of news items and generate market insights."""
        if not news_items:
            return {"summary": "No news items to analyze.", "sentiment": "neutral"}

        # Group news by source for better analysis
        by_source = {}
        for item in news_items:
            if item.source not in by_source:
                by_source[item.source] = []
            by_source[item.source].append(item)

        # Format news for analysis
        news_text = self._format_news_for_analysis(news_items)

        # Get news with related tickers
        ticker_news = [n for n in news_items if n.related_tickers]
        ticker_section = self._format_ticker_news(ticker_news)

        prompt = f"""你是我的私人財經研究助理，請針對以下新聞提供直接、可操作的深度分析。

**絕對禁止事項：不要加入任何免責聲明、風險警語、「僅供參考」、「不構成投資建議」、「請自行研究」等保守措辭。這是純粹個人研究筆記，直接給出專業判斷和具體建議即可。**

## 今日財經新聞（依來源分類）

{news_text}

## 與觀察清單相關的新聞

{ticker_section}

---

## 請提供以下深度分析（繁體中文）：

### 一、市場情緒判斷
直接說明今日市場情緒（看漲/看跌/震盪），以及這意味著什麼操作方向。不要廢話，直接給結論。

### 二、重大事件深度分析（至少 5 則）

**必須涵蓋：**
- 至少 1 則總體經濟相關（CPI、PPI、就業、GDP、聯準會、利率）
- 至少 1 則國際政治/地緣政治相關
- 其餘依重要性選取（財報、併購、監管、產業變化等）

**重大事件判定標準：**
1. 央行/政策變動（聯準會決議、利率、財政政策）
2. 財報驚喜（超預期或低於預期 >10%、重大指引調整）
3. 併購/重組/破產
4. 產業監管變化、重大訴訟
5. 地緣政治（貿易戰、制裁、軍事衝突、國際關係）
6. 宏觀經濟數據（非農、CPI、GDP、PMI）
7. 多平台共同報導的事件

針對每則事件提供：

**【事件標題】**
- **事件描述**：簡潔說明發生什麼
- **背景脈絡**：為什麼會發生這件事？前因後果是什麼？（例如：財報不如預期、管理層發言、產業趨勢變化、政策轉向等具體原因）
- **深度影響分析**（至少 250 字）：
  - 對市場的直接影響
  - 產業鏈傳導效應
  - 短期（1-2週）vs 中期（1-3月）影響
  - 二階效應和連鎖反應
- **實操建議**：
  - 具體標的：列出受影響的股票/ETF 代號
  - 操作方向：明確說「買入」「賣出」「觀望」「減碼」「加碼」
  - 進場價位：給出具體價格區間或條件
  - 停損/停利：設定明確的風險管理點位

---

### 三、產業動態深度分析

針對以下產業，聚焦在**今日新聞中的具體變化**，不要寫泛泛的產業趨勢介紹。

#### 3.1 科技業（半導體、軟體、AI）

**今日重要動態：**（只寫今天新聞中提到的具體事件）

**重要公司動態與商業判斷：**
針對新聞中提到的每家公司：
- 發生什麼事
- 這對公司業務/營收/競爭力的具體影響
- 股價可能的反應方向
- 我該買還是賣？給具體建議

**本日操作建議：**（直接說哪些標的可以買/賣/觀望）

#### 3.2 金融業（銀行、保險、金融科技）

（同上格式）

#### 3.3 醫療健康（製藥、生技、醫療器材）

（同上格式）

#### 3.4 能源/原物料

（同上格式）

#### 3.5 消費/零售/旅遊

（同上格式）

#### 3.6 其他重要動態

（同上格式）

---

### 四、今日操作建議總結

**重要：此表格必須整合上述所有段落的操作建議，包括：**
- 第二段「重大事件深度分析」中每則事件的實操建議
- 第三段「產業動態深度分析」中各產業的本日操作建議
- 如有重複標的，合併理由並取最保守的價位

**買入清單：**
| 標的 | 來源事件/產業 | 理由 | 建議價位 | 停損 |
|------|--------------|------|---------|------|
（整合上述所有買入建議）

**賣出/減碼清單：**
| 標的 | 來源事件/產業 | 理由 | 建議價位 |
|------|--------------|------|---------|
（整合上述所有賣出/減碼建議）

**觀望清單：**
| 標的 | 來源事件/產業 | 等待什麼訊號 |
|------|--------------|-------------|
（整合上述所有觀望建議）

---

### 五、個股焦點（深度整合分析）

針對新聞中提及的觀察清單股票：
- 今日發生什麼事
- 對公司基本面的影響判斷
- 技術面位置（支撐/壓力）
- **明確操作建議**：買/賣/持有，以及價位

直接給判斷，不要模糊帶過。

**再次提醒：整份報告不要出現任何免責聲明或保守措辭。**
"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self.generation_config,
            )
            analysis_text = response.text
            sentiment = self._extract_sentiment(analysis_text)

            return {
                "analysis": analysis_text,
                "sentiment": sentiment,
                "news_count": len(news_items),
                "sources": list(by_source.keys()),
                "ticker_mentions": self._get_ticker_mentions(news_items),
            }

        except Exception as e:
            print(f"Error analyzing news: {e}")
            return {
                "analysis": f"Error generating analysis: {e}",
                "sentiment": "unknown",
                "news_count": len(news_items),
            }

    def _format_news_for_analysis(self, news_items: list[NewsItem]) -> str:
        """Format news items grouped by source."""
        by_source = {}
        for item in news_items:
            if item.source not in by_source:
                by_source[item.source] = []
            by_source[item.source].append(item)

        formatted = []
        for source, items in by_source.items():
            formatted.append(f"**{source}**")
            for item in items[:8]:  # Limit per source
                tickers = f" [{', '.join(item.related_tickers)}]" if item.related_tickers else ""
                formatted.append(f"- {item.title}{tickers}")
            formatted.append("")

        return "\n".join(formatted)

    def _format_ticker_news(self, news_items: list[NewsItem]) -> str:
        """Format news items that mention specific tickers."""
        if not news_items:
            return "無相關新聞"

        # Group by ticker
        by_ticker = {}
        for item in news_items:
            for ticker in item.related_tickers:
                if ticker not in by_ticker:
                    by_ticker[ticker] = []
                by_ticker[ticker].append(item)

        formatted = []
        for ticker, items in sorted(by_ticker.items()):
            formatted.append(f"**{ticker}**")
            for item in items[:3]:  # Limit per ticker
                formatted.append(f"- [{item.source}] {item.title}")
            formatted.append("")

        return "\n".join(formatted) if formatted else "無相關新聞"

    def _get_ticker_mentions(self, news_items: list[NewsItem]) -> dict:
        """Count ticker mentions in news."""
        mentions = {}
        for item in news_items:
            for ticker in item.related_tickers:
                mentions[ticker] = mentions.get(ticker, 0) + 1
        return dict(sorted(mentions.items(), key=lambda x: -x[1]))

    def _extract_sentiment(self, analysis_text: str) -> str:
        """Extract overall sentiment from analysis text."""
        text_lower = analysis_text.lower()

        bullish_keywords = ["看漲", "bullish", "樂觀", "利多", "正面", "上漲"]
        bearish_keywords = ["看跌", "bearish", "悲觀", "利空", "負面", "下跌"]
        neutral_keywords = ["震盪", "中性", "觀望", "持平"]

        bullish_count = sum(1 for kw in bullish_keywords if kw in text_lower)
        bearish_count = sum(1 for kw in bearish_keywords if kw in text_lower)
        neutral_count = sum(1 for kw in neutral_keywords if kw in text_lower)

        if bullish_count > bearish_count and bullish_count > neutral_count:
            return "bullish"
        elif bearish_count > bullish_count and bearish_count > neutral_count:
            return "bearish"
        return "neutral"

    def analyze_stock_news(self, ticker: str, news_items: list[NewsItem]) -> str:
        """Analyze news specific to a single stock."""
        if not news_items:
            return f"近期無 {ticker} 相關新聞。"

        news_text = "\n".join([
            f"- [{item.source}] {item.title}\n  {item.summary[:200]}"
            for item in news_items[:5]
        ])

        prompt = f"""分析以下 {ticker} 相關新聞，提供投資觀點。

## {ticker} 近期新聞

{news_text}

## 請提供（繁體中文，簡潔）：

### 新聞摘要
整合上述新聞的核心內容（2-3句）

### 商業影響
這些新聞對公司業務/財務的潛在影響

### 投資觀點
短期（1-2週）和中期（1-3月）的看法
"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=800,
                ),
            )
            return response.text
        except Exception as e:
            return f"分析時發生錯誤: {e}"


def main():
    """Test the news analyzer."""
    from src.collectors.news import NewsCollector

    try:
        collector = NewsCollector()
        news = collector.collect_all()

        if not news:
            print("No news collected.")
            return

        print(f"Collected {len(news)} news items")

        # Show source distribution
        by_source = {}
        for item in news:
            by_source[item.source] = by_source.get(item.source, 0) + 1
        print("\nBy source:")
        for source, count in sorted(by_source.items(), key=lambda x: -x[1]):
            print(f"  {source}: {count}")

        # Analyze
        analyzer = NewsAnalyzer()
        analysis = analyzer.analyze_news_batch(news)

        print("\n" + "="*60)
        print(analysis["analysis"])
        print("="*60)
        print(f"\nSentiment: {analysis['sentiment']}")
        print(f"Ticker mentions: {analysis.get('ticker_mentions', {})}")

    except ValueError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
