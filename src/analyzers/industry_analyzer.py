"""
Industry Analyzer Module
Implements the 6-prompt pipeline for weekly industry cognition report.

Pipeline:
1. Role & Principles Setup
2. Data Preprocessing & Classification
3. Paradigm Shift Analysis
4. Technology Progress Analysis
5. Company Moves Analysis
6. Final Report Generation
"""
from google import genai
from google.genai import types
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import json


from src.config.settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
)
from src.collectors.base import IntelItem


@dataclass
class AnalysisResult:
    """Container for multi-step analysis results."""
    # Step 2: Data classification
    classified_data: dict = field(default_factory=dict)
    high_signal_events: list = field(default_factory=list)

    # Step 3: Paradigm shifts
    paradigm_shifts: list = field(default_factory=list)

    # Step 4: Technology analysis
    tech_analysis: str = ""

    # Step 5: Company analysis
    company_analysis: str = ""

    # Step 6: Final report
    final_report: str = ""

    # Metadata
    processing_time: float = 0.0
    token_usage: dict = field(default_factory=dict)


class IndustryAnalyzer:
    """
    Analyzes industry intelligence using a multi-step prompt pipeline.

    Designed for the Saturday Weekly Industry Cognition Report.
    """

    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not set in environment")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model = GEMINI_MODEL

    def analyze(
        self,
        intel_items: list[IntelItem],
        run_full_pipeline: bool = True,
    ) -> AnalysisResult:
        """
        Run the full analysis pipeline.

        Args:
            intel_items: List of intelligence items
            run_full_pipeline: If False, only runs classification step

        Returns:
            AnalysisResult with all analysis outputs
        """
        import time
        start_time = time.time()

        result = AnalysisResult()

        # Format raw data
        raw_data = self._format_raw_data(intel_items)

        # Step 2: Classify and identify high-signal events
        print("🔍 Step 2: Classifying data and identifying high-signal events...")
        classification = self._step2_classify_data(raw_data)
        result.classified_data = classification.get("classified", {})
        result.high_signal_events = classification.get("high_signal_events", [])

        if not run_full_pipeline:
            return result

        # Step 3: Analyze paradigm shifts
        print("🔄 Step 3: Analyzing paradigm shifts...")
        result.paradigm_shifts = self._step3_paradigm_shifts(
            result.high_signal_events
        )

        # Step 4: Analyze technology progress
        print("💻 Step 4: Analyzing technology frontier...")
        result.tech_analysis = self._step4_technology_analysis(
            raw_data, result.high_signal_events
        )

        # Step 5: Analyze company moves
        print("🏢 Step 5: Analyzing company moves...")
        result.company_analysis = self._step5_company_analysis(
            raw_data, result.high_signal_events
        )

        # Step 6: Generate final report
        print("📝 Step 6: Generating final report...")
        result.final_report = self._step6_final_report(
            result.high_signal_events,
            result.paradigm_shifts,
            result.tech_analysis,
            result.company_analysis,
        )

        result.processing_time = time.time() - start_time
        print(f"✅ Analysis complete in {result.processing_time:.1f}s")

        return result

    def _format_raw_data(self, intel_items: list[IntelItem]) -> str:
        """Format raw intelligence data for prompts."""
        lines = []

        # Group by source type
        by_type = {}
        for item in intel_items:
            st = item.source_type.value
            if st not in by_type:
                by_type[st] = []
            by_type[st].append(item)

        type_labels = {
            "news": "新聞報導",
            "sec_filing": "SEC 財報/公告",
            "research_paper": "研究論文",
            "clinical_trial": "臨床試驗",
            "regulatory": "監管公告",
        }

        for source_type, items in by_type.items():
            label = type_labels.get(source_type, source_type)
            lines.append(f"\n### {label}\n")

            for item in items[:50]:  # Limit per type
                date_str = item.published.strftime("%m/%d")
                entities = ", ".join(item.related_entities[:3]) if item.related_entities else ""
                tickers = ", ".join([f"${t}" for t in item.related_tickers[:3]]) if item.related_tickers else ""
                tags = f" [{entities}]" if entities else (f" [{tickers}]" if tickers else "")

                lines.append(f"- [{date_str}] [{item.source}] {item.title}{tags}")
                if item.summary:
                    summary = item.summary[:200] + "..." if len(item.summary) > 200 else item.summary
                    lines.append(f"  {summary}")

        return "\n".join(lines)

    def _step2_classify_data(self, raw_data: str) -> dict:
        """
        Step 2: Classify data and identify high-signal events.

        Categories:
        a) 直接事實 (observable facts)
        b) 行為訊號 (actions / decisions)
        c) 約束或激勵線索 (constraints / incentives)
        d) 噪音或重複資訊
        """
        prompt = f"""你是一位世界級全產業、商業與科技研究合夥人。

**【本步驟限制】**
- 不允許進行任何第一性原則、宏觀解釋或高階推論
- 不允許使用「本質上」「從根本上」等抽象語言
- 任務僅限於訊號分類與重要性篩選

---

以下是本週收集的原始資料（新聞、研究、財報、臨床試驗、監管公告）：

{raw_data}

---

請先不要寫報告。請你先做三件事：

## 1. 將資料分類為：

a) **直接事實（observable facts）**
   - 可驗證的數據、公告、結果

b) **行為訊號（actions / decisions）**
   - 公司的具體行動、策略決策、人事變動

c) **約束或激勵的線索（constraints / incentives）**
   - 透露限制、壓力、或動機的資訊

d) **噪音或重複資訊**
   - 價值不高或重複的內容

## 2. 指出哪些資訊：

- **會改變行業「認知地圖」** - 顛覆既有假設或開啟新可能
- **只是確認既有趨勢** - 符合預期，強化現有判斷
- **目前無法判斷價值** - 需要更多資訊才能評估

## 3. 明確列出：

**本週最重要的 5-8 個「高信號事件」**

對每個事件說明：
- 事件摘要（一句話）
- 為何選它而非其他資訊
- 它屬於上述哪個分類
- 它會改變認知地圖還是確認趨勢

請以結構化格式（JSON-like）回答，方便後續處理。使用繁體中文。"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=4000,
                ),
            )
            return {"raw_response": response.text, "high_signal_events": [], "classified": {}}
        except Exception as e:
            return {"error": str(e), "high_signal_events": [], "classified": {}}

    def _step3_paradigm_shifts(self, high_signal_events: list) -> list:
        """
        Step 3: Analyze paradigm shifts from high-signal events.
        """
        # Use the raw response from step 2 which contains high signal events
        events_text = high_signal_events if isinstance(high_signal_events, str) else str(high_signal_events)

        prompt = f"""基於以下高信號事件的分析：

{events_text}

---

**【範式移轉判斷的必要條件】**

在判斷任何「範式移轉」時，你必須先回答以下第一性原則問題，否則不得宣稱為範式移轉：

1. 該行業中，哪一個「不可壓縮的基本約束」正在改變？
   （例如：物理限制、經濟下限、時間、風險、合規、認知成本）

2. 該約束過去為何不可突破？現在是什麼改變讓它鬆動？

3. 若忽略當前產品、公司與敘事，從第一性原則重新推導，行業結構是否必然改寫？

請明確標註：【First-principles lens】並用不超過 3 句話完成。

---

請回答：

## 1. 是否存在以下類型的變化（如有，請明確指出）：

- **成本曲線改變** - 某項能力的成本結構發生質變
- **性能/效率曲線躍遷** - 技術能力出現階躍式提升
- **供給或配額約束改變** - 資源、產能、准入的限制變化
- **合規/法律邊界移動** - 監管框架的實質改變
- **組織或平台治理方式轉變** - 權力結構或決策模式改變

## 2. 將這些變化表述為「從 A → B」的範式移轉句型

例如：
- 從「工具型 AI」→「自治工作代理」
- 從「減重藥物」→「代謝疾病平台」
- 從「晶片供應商」→「AI 基礎設施壟斷者」

## 3. 對每一個潛在範式移轉，說明：

| 項目 | 說明 |
|------|------|
| **驅動機制** | 是什麼（不是事件）在推動這個變化？ |
| **重新定價** | 哪些角色/公司/能力會被重新定價？誰受益？誰受損？ |
| **時間尺度** | 短期（<6月）/ 中期（6-18月）/ 長期（>18月） |
| **信心程度** | 高（有明確證據）/ 中（合理推論）/ 低（早期假說） |

請使用繁體中文，以顧問語言撰寫。明確區分【事實】【推論】【假說】。"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=3000,
                ),
            )
            return [{"raw_response": response.text}]
        except Exception as e:
            return [{"error": str(e)}]

    def _step4_technology_analysis(self, raw_data: str, high_signal_events) -> str:
        """
        Step 4: Analyze technology progress with workflow focus.
        """
        prompt = f"""你是一位世界級科技研究合夥人。

**【本步驟的第一性原則要求】**

在分析任何技術影響時，你必須先做「第一性原則下的工作拆解」：

- 該工作的不可再分單位（irreducible unit）是什麼？
- 人類過去為何必須親自完成這一單位？
- 技術現在是替代、加速，還是重構這一單位？

**禁止：**
- 從功能清單或工具特性出發
- 使用「效率提升」「更聰明」等模糊詞彙

---

基於以下資料，分析本週的技術進展：

{raw_data[:8000]}

---

對於所有技術相關進展（AI、晶片、生技平台、軟體工具）：

**請不要描述技術本身，而是用以下結構輸出：**

## 技術進展分析

對每項重要技術進展：

### [技術/產品名稱]

**1. Capability Delta（能力差分）**
- 新增了什麼「以前做不到」或「成本不可接受」的能力？
- 量化差距（如果有數據）

**2. Workflow Rewrite（工作流如何被改寫）**
- 哪些具體工作環節被替代 / 重構 / 加速？
- Before vs After 是什麼？
- 誰的工作受影響最大？

**3. Elite Usage Pattern（頂尖人才怎麼用）**
- 任務如何被拆解？
- Agent / 工具如何被編排？
- 哪些工作仍必須由人承擔？為什麼？

**4. New Bottleneck（新瓶頸）**
- 問題從哪裡轉移到哪裡？
- 下一個需要突破的是什麼？

---

請聚焦在對工作方式有實質影響的技術，忽略純學術或遠期的進展。
使用繁體中文，顧問語言。"""

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
            return f"技術分析生成錯誤: {e}"

    def _step5_company_analysis(self, raw_data: str, high_signal_events) -> str:
        """
        Step 5: Analyze company moves and strategic implications.
        """
        prompt = f"""你是一位世界級企業策略研究合夥人。

**【本步驟的必要輸出】**

在分析公司策略時，請明確指出至少一個：
【Constraint that cannot be negotiated】

例如：
- 資本結構
- 算力 / 供應鏈
- 監管風險
- 組織治理成本

---

基於以下資料，分析本週重要公司的動態：

{raw_data[:8000]}

---

對每一家出現的重要公司，請用以下語法分析：

## 公司動態分析

### [公司名稱]

**1. 表層動作**
- 他們做了什麼？（具體事實）

**2. 隱含約束**
- 這個動作透露了什麼限制或壓力？
- 為什麼是現在？為什麼是這個選擇？

**3. 戰略意圖**
- **守什麼？** - 保護哪些核心資產或地位
- **打什麼？** - 進攻哪些新市場或對手
- **延遲什麼？** - 刻意推遲或迴避什麼

**4. 對產業的外溢影響**
- **供應鏈** - 上下游會如何反應？
- **競爭者** - 對手必須如何回應？
- **客戶** - 客戶的選擇如何改變？

**5. 下一個可觀測信號**
- 什麼事件發生，代表你的判斷是對的？
- 什麼事件發生，代表你的判斷是錯的？
- 時間框架是多久？

---

只分析有重大動作的公司（3-5 家），不要列出所有提及的公司。
使用繁體中文，顧問語言。明確區分【事實】【推論】【假說】。"""

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
            return f"公司分析生成錯誤: {e}"

    def _step6_final_report(
        self,
        high_signal_events,
        paradigm_shifts: list,
        tech_analysis: str,
        company_analysis: str,
    ) -> str:
        """
        Step 6: Generate the final weekly industry cognition report.
        """
        # Compile previous analyses
        events_text = high_signal_events.get("raw_response", "") if isinstance(high_signal_events, dict) else str(high_signal_events)
        shifts_text = paradigm_shifts[0].get("raw_response", "") if paradigm_shifts else ""

        prompt = f"""你是一位世界級全產業、商業與科技研究合夥人。
你的讀者是頂尖的全球管理顧問與投資顧問：
- 他們學習速度極快
- 但不預設熟悉任何單一產業
- 對「資訊重述」零容忍，只關心「認知是否被更新」

基於以下分析結果，生成最終的【每週產業認知更新報告】：

## 高信號事件分析
{events_text[:3000]}

## 範式移轉分析
{shifts_text[:2000]}

## 技術前沿分析
{tech_analysis[:2000]}

## 公司動態分析
{company_analysis[:2000]}

---

請生成報告，結構必須嚴格包含以下章節：

# 每週產業認知更新報告

## 0. This Week's Thesis
（一句話總結本週最重要的認知更新）

## 1. Executive Brief
（8 條高密度洞察，每條 1-2 句話）
- 格式：[產業標籤] 洞察內容

## 2. Paradigm Shift Radar
（本週識別到的範式移轉信號）
- 使用「從 A → B」句型
- 標注信心程度和時間尺度

## 3. Industry Cognition Map Updates
（哪些行業認知需要更新）
- 舊認知 vs 新認知
- 更新原因

## 4. Technology Frontier
（技術進展，聚焦工作改寫）
- 只列出會實質改變工作方式的技術
- 使用 Capability Delta + Workflow Rewrite 框架

## 5. Company Moves & Strategic Implications
（重要公司動態及其策略含義）
- 表層動作 → 隱含約束 → 戰略意圖
- 外溢影響

## 6. IP / Regulation / Talent Signals
（如有相關資訊）
- 專利動態
- 監管變化
- 人才流動

## 7. Key Metrics & Benchmarks
（本週重要數據點）
- 用表格呈現
- 標注與上週/預期的比較

## 8. Watchlist & Scenarios
（未來 4-12 週關注事項）
- 待驗證的假說
- 關鍵觀察指標
- 情境推演

---

寫作要求：
- 使用顧問語言，而非媒體語言
- 明確區分【事實】【推論】【不確定但值得追蹤的假說】
- 不使用新聞式形容詞（如「震驚」「重磅」）
- 假設讀者時間極其有限
- 使用繁體中文"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.4,
                    max_output_tokens=8000,
                ),
            )
            return response.text
        except Exception as e:
            return f"報告生成錯誤: {e}"

    def quick_analysis(self, intel_items: list[IntelItem]) -> str:
        """
        Quick single-prompt analysis for testing or simpler use cases.
        """
        raw_data = self._format_raw_data(intel_items)

        prompt = f"""你是一位世界級全產業研究合夥人。

以下是本週的情報資料：

{raw_data[:10000]}

---

請生成一份精簡的【每週產業認知更新】，包含：

1. **本週主題**（一句話）

2. **五大高信號事件**
   - 事件摘要
   - 為何重要（So what?）

3. **範式移轉信號**（如有）
   - 從 A → B 的變化
   - 信心程度

4. **公司動態重點**（2-3 家）
   - 動作 + 戰略意圖

5. **下週關注**
   - 待驗證假說
   - 觀察指標

使用繁體中文，顧問語言，800-1000 字。"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=3000,
                ),
            )
            return response.text
        except Exception as e:
            return f"分析生成錯誤: {e}"


def main():
    """Test the industry analyzer."""
    from src.collectors.intel_aggregator import IntelAggregator

    print("\n" + "="*60)
    print("Testing Industry Analyzer")
    print("="*60)

    # Collect data
    aggregator = IntelAggregator()
    items = aggregator.collect_all(days_lookback=7)

    if not items:
        print("No items collected. Exiting.")
        return

    # Quick analysis
    print("\n--- Quick Analysis ---\n")
    analyzer = IndustryAnalyzer()
    quick_result = analyzer.quick_analysis(items[:50])
    print(quick_result)

    # Full pipeline (uncomment to test)
    # print("\n--- Full Pipeline Analysis ---\n")
    # result = analyzer.analyze(items[:50], run_full_pipeline=True)
    # print(result.final_report)


if __name__ == "__main__":
    main()
