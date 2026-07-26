"""
数据集审查 Agent — 独立审查生成结果，不参与生成。

核心理念：不要让同一次 LLM 调用同时生成并自我评价。
Generator 负责生成，Critic 负责审查，两者独立。

审查维度：
  - 教材证据支持度：每条结论是否有 source_ref 支撑
  - 知识图谱一致性：graph_path 节点与边关系是否正确
  - 答案唯一性/任务清晰度：正确答案是否唯一、问题是否有歧义
  - 术语规范性：中英文术语是否与 terms.csv 一致
  - 去重风险：是否与已有数据高度相似
  - 教学/诊断价值：是否有助于学习或发现误区

输出 CriticReview，包含 required_fixes（生成器可以据此修正）。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from infrastructure.llm_client import LLMClient, create_llm_client
from schemas.generation_blueprint import EvidencePackage
from schemas.validation_report import QualityScore

logger = logging.getLogger(__name__)


class CriticReview(BaseModel):
    """Critic 审查结果"""
    item_id: str = ""
    supported_by_sources: bool = False
    source_issues: list[str] = Field(default_factory=list)

    graph_consistent: bool = False
    graph_issues: list[str] = Field(default_factory=list)

    single_best_answer: bool = False
    ambiguity_issues: list[str] = Field(default_factory=list)

    terminology_valid: bool = False
    terminology_issues: list[str] = Field(default_factory=list)

    duplicate_risk: float = Field(default=0.0, ge=0.0, le=1.0)

    teaching_value_comment: str = ""
    overall_comment: str = ""

    quality_score: QualityScore | None = None
    required_fixes: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        """是否通过审查（无致命问题）"""
        return (
            self.supported_by_sources
            and self.graph_consistent
            and self.single_best_answer
            and self.terminology_valid
            and self.duplicate_risk < 0.85
        )


class DatasetCriticAgent:
    """
    数据集审查 Agent。

    与 Generator 独立运行。使用更强的模型（Claude）以确保审查质量。
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self._llm = llm_client or create_llm_client()

    # ═══════════════════════════════════════════════════════════
    # QA 审查
    # ═══════════════════════════════════════════════════════════

    def review_qa(
        self, candidate: dict, evidence: EvidencePackage, existing_items: list[dict] | None = None
    ) -> CriticReview:
        """审查 QA 候选题目"""
        prompt = self._build_qa_review_prompt(candidate, evidence, existing_items or [])
        system = self._critic_system_prompt()

        raw = self._llm.chat(prompt, system=system, temperature=0.2)
        return self._parse_review(raw, candidate.get("id", ""))

    def _build_qa_review_prompt(
        self, candidate: dict, evidence: EvidencePackage, existing: list[dict]
    ) -> str:
        """构建 QA 审查 prompt"""
        options_text = "\n".join(
            f"{k}: {v}" for k, v in candidate.get("options", {}).items()
        )

        return f"""请审查以下 AI 生成的 QA 题目。

══════════════════════════════════════
【候选题目】
══════════════════════════════════════
ID: {candidate.get('id', '')}
类型: {candidate.get('question_type', '')}
难度: {candidate.get('difficulty', '')}
题目: {candidate.get('question', '')}
选项:
{options_text}
正确答案: {candidate.get('answer', '')}
参考答案: {candidate.get('reference_answer', '')}
关键知识点: {', '.join(candidate.get('key_points', []))}
教材引用: {json.dumps([{'chunk_id': s.get('chunk_id', ''), 'text': s.get('text', '')[:100]} for s in candidate.get('source_refs', [])], ensure_ascii=False)}
图谱路径: {' → '.join(candidate.get('graph_path', []))}

══════════════════════════════════════
【可用证据】
══════════════════════════════════════
图谱节点: {', '.join(n.label_zh for n in evidence.graph_nodes)}
术语: {', '.join(t.zh for t in evidence.standard_terms)}
已有数据量: {len(existing)}

══════════════════════════════════════
【审查要求】
══════════════════════════════════════
请逐项审查并给出：

1. 教材证据支持度 (0-30分)：参考答案的核心陈述能否从 source_refs 中找到支撑？
2. 知识图谱一致性 (0-20分)：graph_path 的节点是否存在、边关系方向是否正确？
3. 答案唯一性 (0-15分)：正确答案是否唯一、干扰项是否合理区分？
4. 教学价值 (0-15分)：这道题是否有助于学习或发现误区？
5. 与现有数据差异性 (0-10分)：是否与已有数据重复？
6. 术语规范 (0-10分)：中英文术语是否正确？

输出 JSON 格式：
```json
{{
  "supported_by_sources": true,
  "source_issues": [],
  "graph_consistent": true,
  "graph_issues": [],
  "single_best_answer": true,
  "ambiguity_issues": [],
  "terminology_valid": true,
  "terminology_issues": [],
  "duplicate_risk": 0.0,
  "teaching_value_comment": "...",
  "overall_comment": "...",
  "quality_score": {{
    "evidence_support": 25,
    "graph_consistency": 18,
    "answer_clarity": 12,
    "teaching_value": 12,
    "distinctiveness": 8,
    "terminology_accuracy": 9
  }},
  "required_fixes": []
}}
```"""

    # ═══════════════════════════════════════════════════════════
    # 苏格拉底审查
    # ═══════════════════════════════════════════════════════════

    def review_socratic(
        self, candidate: dict, evidence: EvidencePackage
    ) -> CriticReview:
        """审查苏格拉底引导链"""
        steps_summary = []
        for s in candidate.get("steps", []):
            steps_summary.append(
                f"  {s.get('step_id')}: {s.get('question', '')[:80]} "
                f"[correct→{s.get('next_if_correct')}, partial→{s.get('next_if_partial')}, "
                f"wrong→{s.get('next_if_wrong')}]"
            )

        prompt = f"""请审查以下 AI 生成的苏格拉底引导链。

══════════════════════════════════════
【候选苏格拉底链】
══════════════════════════════════════
ID: {candidate.get('id', '')}
标题: {candidate.get('title', '')}
目标知识点: {', '.join(candidate.get('target_knowledge_ids', []))}
触发误区: {', '.join(candidate.get('trigger_misconceptions', []))}
步骤:
{chr(10).join(steps_summary)}
完成条件: {json.dumps(candidate.get('completion_condition', {}), ensure_ascii=False)}
图谱路径: {' → '.join(candidate.get('graph_path', []))}

══════════════════════════════════════
【可用证据】
══════════════════════════════════════
图谱节点: {', '.join(n.label_zh for n in evidence.graph_nodes)}
图谱边: {', '.join(f'{e.source}→{e.target}' for e in evidence.graph_edges)}

══════════════════════════════════════
【审查重点】
══════════════════════════════════════
1. 每一步是否只推进一个认知环节（不跳跃）？
2. 问题是否直接泄露了最终答案？
3. 步骤之间的 kg_node_ref 是否对应知识图谱中的相邻节点？
4. 分支指针是否正确（无悬空指针）？
5. 完成条件是否覆盖全部因果链关键概念？

输出 JSON 格式（同 QA 审查）。"""

        system = self._critic_system_prompt()
        raw = self._llm.chat(prompt, system=system, temperature=0.2)
        return self._parse_review(raw, candidate.get("id", ""))

    # ═══════════════════════════════════════════════════════════
    # 费曼审查
    # ═══════════════════════════════════════════════════════════

    def review_feynman(
        self, candidate: dict, evidence: EvidencePackage
    ) -> CriticReview:
        """审查费曼任务"""
        prompt = f"""请审查以下 AI 生成的费曼任务。

══════════════════════════════════════
【候选费曼任务】
══════════════════════════════════════
ID: {candidate.get('id', '')}
主题: {candidate.get('topic', '')}
费曼挑战: {candidate.get('prompt', '')}
听众: {candidate.get('audience', '')}
必须覆盖: {', '.join(candidate.get('mandatory_points', []))}
加分点: {', '.join(candidate.get('optional_points', []))}
禁止陈述: {', '.join(candidate.get('forbidden_claims', []))}
评分清单: {json.dumps([c.get('point', '') for c in candidate.get('checklist', [])], ensure_ascii=False)}
优秀范例: {candidate.get('excellent_example', '')[:200]}

══════════════════════════════════════
【审查重点】
══════════════════════════════════════
1. mandatory_points 是否覆盖因果链的所有关键环节？
2. forbidden_claims 是否确实是常见错误（不是随意编造）？
3. checklist 是否与 mandatory_points 一一对应？
4. excellent_example 是否展示了所有 mandatory_points？
5. 评分标准是否合理可操作？

输出 JSON 格式（同 QA 审查）。"""

        system = self._critic_system_prompt()
        raw = self._llm.chat(prompt, system=system, temperature=0.2)
        return self._parse_review(raw, candidate.get("id", ""))

    # ═══════════════════════════════════════════════════════════
    # 通用方法
    # ═══════════════════════════════════════════════════════════

    def _critic_system_prompt(self) -> str:
        return """你是材料科学教育领域的严格审查员。你的任务是找问题，不是夸奖。

【审查原则】
1. 宁严勿宽：有疑问的地方标记出来
2. 事实错误直接拒绝：如果候选数据包含与教材/图谱矛盾的事实，标记 supported_by_sources=false
3. 图谱冲突直接拒绝：如果 graph_path 的边关系方向错误，标记 graph_consistent=false
4. 术语必须查表：如果术语不在标准术语表中，标记 terminology_valid=false
5. 答案必须唯一：如果干扰项不清晰或正确答案有争议，标记 single_best_answer=false

【评分标准】
- evidence_support (0-30): 每条关键陈述有 source_ref 支撑 → 25+；部分有支撑 → 15-24；几乎没有 → <15
- graph_consistency (0-20): 路径完整且边方向正确 → 18+；节点存在但边有问题 → 10-17；节点不存在 → <10
- answer_clarity (0-15): 答案唯一、无歧义 → 12+；有小歧义 → 8-11；严重歧义 → <8
- teaching_value (0-15): 有助于诊断误区或深化理解 → 12+；普通 → 8-11；无价值 → <8
- distinctiveness (0-10): 高度原创 → 8+；与已有数据有些重叠 → 5-7；明显重复 → <5
- terminology_accuracy (0-10): 全部正确 → 9+；1-2个小错 → 6-8；多处错误 → <6"""

    def _parse_review(self, raw: str, item_id: str) -> CriticReview:
        """解析 Critic LLM 输出"""
        # 提取 JSON 块
        json_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        matches = re.findall(json_pattern, raw, re.DOTALL)
        json_str = matches[-1] if matches else raw

        try:
            data = json.loads(json_str.strip())
        except json.JSONDecodeError:
            start = json_str.find("{")
            if start >= 0:
                depth = 0
                end = start
                for i in range(start, len(json_str)):
                    if json_str[i] == "{":
                        depth += 1
                    elif json_str[i] == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                try:
                    data = json.loads(json_str[start:end])
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse critic output for {item_id}")
                    return CriticReview(item_id=item_id)
            else:
                logger.error(f"No JSON found in critic output for {item_id}")
                return CriticReview(item_id=item_id)

        # 构建 QualityScore
        qs_data = data.get("quality_score", {})
        quality_score = None
        if qs_data:
            quality_score = QualityScore(
                evidence_support=float(qs_data.get("evidence_support", 0)),
                graph_consistency=float(qs_data.get("graph_consistency", 0)),
                answer_clarity=float(qs_data.get("answer_clarity", 0)),
                teaching_value=float(qs_data.get("teaching_value", 0)),
                distinctiveness=float(qs_data.get("distinctiveness", 0)),
                terminology_accuracy=float(qs_data.get("terminology_accuracy", 0)),
            )

        return CriticReview(
            item_id=item_id,
            supported_by_sources=data.get("supported_by_sources", False),
            source_issues=data.get("source_issues", []),
            graph_consistent=data.get("graph_consistent", False),
            graph_issues=data.get("graph_issues", []),
            single_best_answer=data.get("single_best_answer", False),
            ambiguity_issues=data.get("ambiguity_issues", []),
            terminology_valid=data.get("terminology_valid", False),
            terminology_issues=data.get("terminology_issues", []),
            duplicate_risk=float(data.get("duplicate_risk", 0.0)),
            teaching_value_comment=data.get("teaching_value_comment", ""),
            overall_comment=data.get("overall_comment", ""),
            quality_score=quality_score,
            required_fixes=data.get("required_fixes", []),
        )


def create_critic_agent() -> DatasetCriticAgent:
    """工厂函数"""
    return DatasetCriticAgent()
