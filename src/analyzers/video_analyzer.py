"""
Video Analyzer Module
Uses Gemini AI to analyze and summarize YouTube videos.
"""
from google import genai
from google.genai import types


from src.config.settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_TEMPERATURE,
    GEMINI_MAX_OUTPUT_TOKENS,
)
from src.collectors.youtube import YouTubeVideo


class VideoAnalyzer:
    """Analyzes YouTube videos using Gemini AI."""

    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not set in environment")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model = GEMINI_MODEL
        self.generation_config = types.GenerateContentConfig(
            temperature=GEMINI_TEMPERATURE,
            max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
        )

    def analyze_video(self, video: YouTubeVideo) -> dict:
        """Analyze a single video and generate summary."""
        if not video.transcript:
            return {
                "summary": "無法取得影片字幕",
                "key_points": [],
                "stocks_mentioned": [],
                "market_view": "",
            }

        prompt = f"""分析以下 YouTube 財經影片，提供簡潔摘要。

## 影片資訊
- 標題: {video.title}
- 頻道: {video.channel_name}
- 時長: {video.duration}

## 字幕內容
{video.transcript[:25000]}

## 請提供（繁體中文，簡潔扼要）：

### 核心觀點（50-100字）
這部影片的主要論點是什麼？

### 關鍵要點（3-5點，每點一句話）
-

### 提及的投資標的
列出影片中提及的股票/ETF及觀點（看漲/看跌/中性）

### 市場判斷
創作者對近期市場的整體看法（一句話）
"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=1500,
                ),
            )

            return {
                "video_id": video.video_id,
                "title": video.title,
                "channel": video.channel_name,
                "url": video.url,
                "duration": video.duration,
                "analysis": response.text,
            }

        except Exception as e:
            print(f"Error analyzing video {video.title}: {e}")
            return {
                "video_id": video.video_id,
                "title": video.title,
                "channel": video.channel_name,
                "url": video.url,
                "duration": video.duration,
                "analysis": f"分析時發生錯誤: {e}",
            }

    def generate_video_summaries(self, videos: list[YouTubeVideo], collector) -> str:
        """Generate summaries for videos with transcripts."""
        if not videos:
            return "過去 24 小時內沒有追蹤頻道的新影片。"

        lines = ["## 📺 YouTube 財經頻道更新\n"]

        # Group by category
        by_category = {}
        for video in videos:
            cat = video.category or "其他"
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(video)

        category_names = {
            "us_stocks": "美股財經",
            "macro_economics": "總體經濟",
            "geopolitics": "地緣政治",
            "tech_ai": "科技/AI",
            "business_analysis": "商業分析",
            "interviews": "訪談",
            "financial_media": "財經媒體",
        }

        analyzed_count = 0
        max_analyze = 5  # Limit API calls

        for category, cat_videos in by_category.items():
            cat_name = category_names.get(category, category)
            lines.append(f"\n### {cat_name}\n")

            for video in cat_videos:
                lines.append(f"#### [{video.channel_name}] {video.title}")
                lines.append(f"🔗 [觀看影片]({video.url}) | ⏱️ {video.duration}\n")

                # Get transcript and analyze (limited)
                if analyzed_count < max_analyze:
                    video.transcript = collector.get_transcript(video.video_id)
                    if video.transcript:
                        analysis = self.analyze_video(video)
                        lines.append(analysis.get("analysis", "無法生成摘要"))
                        analyzed_count += 1
                    else:
                        lines.append("*（無字幕，無法生成摘要）*")
                else:
                    lines.append("*（待分析）*")

                lines.append("")  # Empty line between videos

        return "\n".join(lines)

    def generate_quick_list(self, videos: list[YouTubeVideo]) -> str:
        """Generate a quick list of new videos without full analysis."""
        if not videos:
            return "過去 24 小時內沒有追蹤頻道的新影片。"

        lines = ["## 📺 新影片快覽\n"]

        for video in videos[:10]:  # Limit to 10
            lines.append(
                f"- **{video.channel_name}**: [{video.title}]({video.url}) ({video.duration})"
            )

        return "\n".join(lines)


def main():
    """Test the video analyzer."""
    from src.collectors.youtube import YouTubeCollector

    try:
        collector = YouTubeCollector()
        videos = collector.collect_all()

        if not videos:
            print("No videos collected.")
            return

        print(f"\nFound {len(videos)} new videos\n")

        analyzer = VideoAnalyzer()

        # Analyze first video with transcript
        for video in videos[:2]:
            print(f"Getting transcript for: {video.title}")
            video.transcript = collector.get_transcript(video.video_id)
            if video.transcript:
                analysis = analyzer.analyze_video(video)
                print(f"\n=== {video.channel_name}: {video.title} ===")
                print(analysis.get("analysis", "No analysis"))
                print()

    except ValueError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
