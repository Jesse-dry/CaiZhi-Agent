"""
agents/feynman_agent.py — FeynmanAgent: 按 rubric 评价学生解释。

Constrained agent: receives evaluation rubric + student explanation →
5-dimension scoring + identifies covered/missing/incorrect points.

Replaces: feynman_service.evaluate() keyword matching.
Key improvement over V1: can detect INCORRECT statements (V1 only detects
covered/missing via keyword matching, cannot identify wrong claims).

Design:
  - System prompt enforces rubric-based evaluation
  - Structured output: dimension_scores, covered_points, missing_points,
    incorrect_points (NEW), next_question, feedback
  - V1 fallback: keyword-based checklist matching
"""

from __future__ import annotations

import logging

from schemas.agent import AgentContext, AgentResult, AgentTrace, AgentEvidence
from agents.base import (
    _parse_structured_output,
    _build_system_prompt,
    _extract_evidence,
    _call_llm,
)
from infrastructure.llm_client import LLMClient

logger = logging.getLogger(__name__)

FEYNMAN_PROMPT_VERSION = "1.0"

# ── System prompt sections ──

FEYNMAN_ROLE = """你是《材料科学与工程》专业的费曼学习法评价专家（材智 Agent）。
你的职责是按照给定的评价标准（rubric）来评估学生的费曼解释。
费曼学习法的核心理念是：如果你不能简单地解释清楚一个概念，
说明你还没有真正理解它。

你需要从五个维度进行评价：
1. 概念准确性（18分）：核心概念是否正确
2. 因果链完整性（20分）：是否把'工艺→组织→结构→性能'讲完整
3. 术语规范性（14分）：是否使用了标准术语
4. 表达清晰度（16分）：是否用简单语言解释清楚了
5. 误区控制（10分）：是否出现了明显的错误表述"""

FEYNMAN_CONSTRAINTS = [
    "必须严格按照提供的 checklist 逐条检查",
    "不仅检查学生'说了什么'，还要检查学生'说错了什么'",
    "给分要有依据，不能随便给分",
    "评价要具体，指出哪个概念讲对了、哪个讲错了",
    "用鼓励的语气，同时给出具体的改进建议",
    "用中文回答",
]

FEYNMAN_OUTPUT_FORMAT = {
    "concept_accuracy": "概念准确性得分（0-18）",
    "causal_completeness": "因果链完整性得分（0-20）",
    "term_accuracy": "术语规范性得分（0-14）",
    "clarity": "表达清晰度得分（0-16）",
    "misconception_control": "误区控制得分（0-10）",
    "covered_points": "讲清楚的 checklist 条目列表（字符串数组）",
    "missing_points": "缺失的 checklist 条目列表（字符串数组）",
    "incorrect_points": "表述有误的内容列表（字符串数组，每项描述具体错误）",
    "next_question": "建议下一步思考的问题",
    "feedback": "综合评价和建议（2-4句话）",
    "confidence": "评价信心程度，0.0-1.0",
}


# ═══════════════════════════════════════════════════════════
# FeynmanAgent
# ═══════════════════════════════════════════════════════════

class FeynmanAgent:
    """
    费曼评价 Agent — 按 rubric 评价学生解释。

    可调用资源：费曼评价标准（checklist + excellent_example）、知识图谱
    不可做：主观臆断、不依据 checklist 随意给分

    Usage:
        agent = FeynmanAgent(llm_client)
        result = await agent.run(context)
        # result.structured_data["dimension_scores"] → dict of 5 scores
        # result.structured_data["incorrect_points"] → wrong claims (new in V2!)
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def run(self, context: AgentContext) -> AgentResult:
        """
        评价学生的费曼解释。

        Args:
            context: AgentContext with:
                - student_input: student's explanation text
                - resources.feynman_rubric: evaluation rubric
                - resources.graph_nodes: knowledge graph for cross-reference

        Returns:
            AgentResult with 5-dimension scores + detailed feedback.
        """
        # 1. Build prompts
        system_prompt = _build_system_prompt(
            role=FEYNMAN_ROLE,
            constraints=FEYNMAN_CONSTRAINTS,
            output_format=FEYNMAN_OUTPUT_FORMAT,
        )
        user_prompt = self._build_user_prompt(context)

        # 2. Call LLM
        raw_response = await _call_llm(
            self.llm,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=1536,
        )

        # 3. Parse structured output
        if raw_response:
            structured = _parse_structured_output(raw_response)
            confidence = float(structured.pop("confidence", 0.6))
            # Validate score ranges
            structured = self._validate_scores(structured)
        else:
            structured = self._v1_fallback(context)
            confidence = 0.5

        # Calculate total
        total_score = self._calc_total(structured)

        # 4. Build evidence
        evidence = _extract_evidence(
            structured_data=structured,
            resources_rag_chunks=context.resources.rag_chunks,
            resources_terms=context.resources.terms,
            resources_graph_nodes=context.resources.graph_nodes,
        )

        # 5. Build trace
        trace = AgentTrace(
            reasoning_steps=self._build_reasoning_steps(context, structured, total_score),
            decision_rationale=(
                f"五维度评分总分 {total_score}/78，"
                f"覆盖 {len(structured.get('covered_points', []))} 个检查点，"
                f"缺失 {len(structured.get('missing_points', []))} 个，"
                f"错误 {len(structured.get('incorrect_points', []))} 个"
            ),
            alternatives_considered=[],
            model_name=self.llm.config.model if raw_response else "",
            prompt_version=FEYNMAN_PROMPT_VERSION,
        )

        # 6. Build display content
        content = self._build_content(structured, total_score)

        # Store scores for easy access
        structured["total_score"] = total_score
        structured["dimension_scores"] = {
            "concept_accuracy": structured.get("concept_accuracy", 0),
            "causal_completeness": structured.get("causal_completeness", 0),
            "term_accuracy": structured.get("term_accuracy", 0),
            "clarity": structured.get("clarity", 0),
            "misconception_control": structured.get("misconception_control", 0),
        }

        return AgentResult(
            content=content,
            structured_data=structured,
            evidence=evidence,
            confidence=confidence,
            trace=trace,
        )

    # ── V1 fallback (keyword-based) ──────────────────────────

    def _v1_fallback(self, context: AgentContext) -> dict:
        """Keyword-based checklist matching, mirrors V1 feynman_service."""
        rubric = context.resources.feynman_rubric or {}
        checklist = rubric.get("checklist", [])

        text_lower = context.student_input.lower()
        covered = []
        missing = []

        for item in checklist:
            keywords = item.get("keywords", [])
            point = item.get("point", "")
            if any(kw.lower() in text_lower for kw in keywords):
                covered.append(point)
            else:
                missing.append(point)

        # V1 cannot detect incorrect statements
        return {
            "concept_accuracy": min(18, len(covered) * 3),
            "causal_completeness": min(20, len(covered) * 2),
            "term_accuracy": min(14, len(covered) * 2),
            "clarity": min(16, max(3, len(context.student_input) // 50)),
            "misconception_control": 10,
            "covered_points": covered,
            "missing_points": missing,
            "incorrect_points": [],
            "next_question": "",
            "feedback": (
                f"已覆盖 {len(covered)}/{len(checklist)} 个知识点。"
                f"{'请补充：' + '、'.join(missing[:3]) if missing else '表现优秀！'}"
            ),
        }

    # ── Prompt builder ───────────────────────────────────────

    def _build_user_prompt(self, context: AgentContext) -> str:
        """Build the Feynman evaluation prompt."""
        rubric = context.resources.feynman_rubric or {}
        checklist = rubric.get("checklist", [])
        excellent = rubric.get("excellent_example", "")

        checklist_text = ""
        for i, item in enumerate(checklist):
            point = item.get("point", "")
            keywords = item.get("keywords", [])
            checklist_text += f"  {i + 1}. {point}（关键词：{'、'.join(keywords)}）\n"

        graph_context = ""
        if context.resources.graph_nodes:
            labels = [
                n.get("label_zh", n.get("id", ""))
                for n in context.resources.graph_nodes[:10]
            ]
            graph_context = "、".join(labels)

        return f"""请评价以下学生的费曼解释。

【评价主题】
{rubric.get('topic', '未指定')}

【评分清单】
{checklist_text}

{'【优秀范例参考】' if excellent else ''}
{excellent}

{'【相关知识图谱节点】' if graph_context else ''}
{graph_context}

【学生解释】
{context.student_input}

请逐条对比 checklist，不仅要检查学生'说了什么'，
还要检查'说错了什么'（这是 V1 系统做不到的）。
请严格按照输出格式返回 JSON。"""

    # ── Score validation ─────────────────────────────────────

    def _validate_scores(self, structured: dict) -> dict:
        """Clamp dimension scores to valid ranges."""
        limits = {
            "concept_accuracy": 18,
            "causal_completeness": 20,
            "term_accuracy": 14,
            "clarity": 16,
            "misconception_control": 10,
        }
        for key, max_val in limits.items():
            if key in structured:
                try:
                    structured[key] = max(0, min(max_val, int(structured[key])))
                except (ValueError, TypeError):
                    structured[key] = 0
        return structured

    def _calc_total(self, structured: dict) -> int:
        """Calculate total score from dimension scores."""
        keys = [
            "concept_accuracy", "causal_completeness", "term_accuracy",
            "clarity", "misconception_control",
        ]
        return sum(structured.get(k, 0) for k in keys)

    # ── Output builders ──────────────────────────────────────

    def _build_content(self, structured: dict, total_score: int) -> str:
        """Build display-friendly markdown evaluation."""
        dims = [
            ("概念准确性", structured.get("concept_accuracy", 0), 18),
            ("因果链完整性", structured.get("causal_completeness", 0), 20),
            ("术语规范性", structured.get("term_accuracy", 0), 14),
            ("表达清晰度", structured.get("clarity", 0), 16),
            ("误区控制", structured.get("misconception_control", 0), 10),
        ]

        parts = [f"## 费曼评价结果\n**总分: {total_score}/78**\n"]

        parts.append("### 五维度评分")
        for name, score, max_s in dims:
            bar = "█" * (score * 20 // max_s) + "░" * (20 - score * 20 // max_s)
            parts.append(f"- {name}: {bar} {score}/{max_s}")

        if structured.get("covered_points"):
            parts.append("\n### ✅ 讲清楚的")
            for p in structured["covered_points"]:
                parts.append(f"- {p}")

        if structured.get("missing_points"):
            parts.append("\n### ⚠️ 缺失的")
            for p in structured["missing_points"]:
                parts.append(f"- {p}")

        if structured.get("incorrect_points"):
            parts.append("\n### ❌ 表述有误的")
            for p in structured["incorrect_points"]:
                parts.append(f"- {p}")

        if structured.get("feedback"):
            parts.append(f"\n### 💬 评价\n{structured['feedback']}")

        if structured.get("next_question"):
            parts.append(f"\n### 🤔 继续思考\n{structured['next_question']}")

        return "\n".join(parts)

    def _build_reasoning_steps(
        self, context: AgentContext, structured: dict, total_score: int
    ) -> list[str]:
        """Build reasoning steps for the trace."""
        rubric = context.resources.feynman_rubric or {}
        checklist = rubric.get("checklist", [])
        feynman_id = rubric.get("feynman_id", context.metadata.get("feynman_id", "?"))

        steps = [
            f"评价标准: {feynman_id}，共 {len(checklist)} 条 checklist",
            f"学生解释长度: {len(context.student_input)} 字符",
            f"总分: {total_score}/78",
            f"覆盖 {len(structured.get('covered_points', []))} 条，"
            f"缺失 {len(structured.get('missing_points', []))} 条，"
            f"错误 {len(structured.get('incorrect_points', []))} 条",
        ]
        if structured.get("incorrect_points"):
            steps.append("检测到错误表述（V1 关键词引擎无法检测此项）")
        return steps
