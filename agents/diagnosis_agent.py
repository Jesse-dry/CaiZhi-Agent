"""
agents/diagnosis_agent.py — DiagnosisAgent: 错误类型识别与知识盲区诊断。

Constrained agent: receives question + student answer + misconception data →
enriches error_reason, feedback, missing_concepts with LLM reasoning
about causal reasoning gaps.

Augments (does NOT replace) knowledge/misconception_mapper.py.
The mapper still provides the base diagnosis; this agent enriches it.

Design:
  - System prompt focuses on causal reasoning gap analysis
  - Structured output: error_reason, feedback, missing_concepts, confidence
  - V1 fallback: returns the pre-mapped diagnosis data unchanged
"""

from __future__ import annotations

import logging

from schemas.agent import AgentContext, AgentResult, AgentTrace
from agents.base import (
    _parse_structured_output,
    _build_system_prompt,
    _extract_evidence,
    _call_llm,
)
from infrastructure.llm_client import LLMClient

logger = logging.getLogger(__name__)

DIAGNOSIS_PROMPT_VERSION = "1.0"

# ── System prompt sections ──

DIAGNOSIS_ROLE = """你是《材料科学与工程》专业的错题诊断专家（材智 Agent）。
你的职责是分析学生为什么会选错答案——不是简单地判断对错，
而是从因果推理链条中找出学生缺失的环节。
学生的错误往往源于某个中间概念没理解透，而不是整条链都不懂。
你需要定位最关键的缺失概念，并用通俗的语言解释为什么错。"""

DIAGNOSIS_CONSTRAINTS = [
    "诊断必须基于提供的误区数据和知识图谱，不得凭空猜测",
    "重点分析因果推理的断裂点：学生卡在哪个推理步骤？",
    "反馈要具体，不能说'你需要加强学习'这种空话",
    "缺失知识点必须来自知识图谱或术语表，不得编造",
    "如果学生回答正确，简单肯定即可，不需要过度分析",
    "用中文回答",
]

DIAGNOSIS_OUTPUT_FORMAT = {
    "error_reason": "学生错误的具体原因（1-2句，从因果推理角度分析）",
    "feedback": "针对性的学习建议（告诉学生从哪个知识点补起）",
    "missing_concepts": "缺失的知识点列表（字符串数组，每个概念名称）",
    "causal_gap": "因果推理链中具体断裂的位置描述",
    "confidence": "诊断信心程度，0.0-1.0",
}


# ═══════════════════════════════════════════════════════════
# DiagnosisAgent
# ═══════════════════════════════════════════════════════════

class DiagnosisAgent:
    """
    错题诊断 Agent — 识别错误类型和知识盲区。

    可调用资源：题库、误区库、知识图谱
    不可做：编造不存在的误区、猜测学生背景

    Usage:
        agent = DiagnosisAgent(llm_client)
        result = await agent.run(context)
        # result.structured_data["error_reason"] → LLM 丰富的错误原因
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def run(self, context: AgentContext) -> AgentResult:
        """
        执行错题诊断。

        Args:
            context: AgentContext with:
                - student_input: student's selected option + answer text
                - resources.misconception_data: pre-mapped diagnosis
                - resources.questions: the question data
                - resources.graph_nodes/edges: knowledge graph

        Returns:
            AgentResult with enriched diagnosis + evidence + trace.
        """
        # 1. Build prompts
        system_prompt = _build_system_prompt(
            role=DIAGNOSIS_ROLE,
            constraints=DIAGNOSIS_CONSTRAINTS,
            output_format=DIAGNOSIS_OUTPUT_FORMAT,
        )
        user_prompt = self._build_user_prompt(context)

        # 2. Call LLM
        raw_response = await _call_llm(
            self.llm,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=1024,
        )

        # 3. Parse + merge with pre-mapped data
        pre_mapped = context.resources.misconception_data or {}
        is_correct = pre_mapped.get("is_correct", False)

        if raw_response and not is_correct:
            llm_structured = _parse_structured_output(raw_response)
            confidence = float(llm_structured.pop("confidence", 0.7))
            # Merge: LLM enriches, pre-mapped provides base
            structured = {
                "error_reason": llm_structured.get("error_reason", pre_mapped.get("error_reason", "")),
                "feedback": llm_structured.get("feedback", pre_mapped.get("feedback", "")),
                "missing_concepts": llm_structured.get("missing_concepts", pre_mapped.get("missing_points", [])),
                "causal_gap": llm_structured.get("causal_gap", ""),
                "is_correct": is_correct,
                "misconception": pre_mapped.get("misconception", ""),
                "ai_enriched": True,
            }
        else:
            # Correct answer or LLM unavailable — use pre-mapped data
            structured = {
                "error_reason": pre_mapped.get("error_reason", ""),
                "feedback": pre_mapped.get("feedback", "回答正确！可以继续进入费曼解释环节。"),
                "missing_concepts": pre_mapped.get("missing_points", []),
                "causal_gap": "",
                "is_correct": is_correct,
                "misconception": pre_mapped.get("misconception", ""),
                "ai_enriched": bool(raw_response),
            }
            confidence = 0.8 if is_correct else 0.5

        # 4. Build evidence
        evidence = _extract_evidence(
            structured_data=structured,
            resources_rag_chunks=context.resources.rag_chunks,
            resources_terms=context.resources.terms,
            resources_graph_nodes=context.resources.graph_nodes,
        )

        # 5. Build trace
        trace = AgentTrace(
            reasoning_steps=self._build_reasoning_steps(context, pre_mapped, structured),
            decision_rationale=(
                f"学生{'回答正确' if is_correct else '选错选项 ' + pre_mapped.get('selected_option', '?')}"
                f"，{'无需深入诊断' if is_correct else '定位到因果推理断裂点'}"
            ),
            alternatives_considered=[
                "仅返回预映射的误区数据" if structured.get("ai_enriched") else "尝试 LLM 丰富但失败，回退到预映射数据"
            ],
            model_name=self.llm.config.model if raw_response else "",
            prompt_version=DIAGNOSIS_PROMPT_VERSION,
        )

        # 6. Build display content
        if is_correct:
            content = "✅ 回答正确！你已掌握这个知识点的核心因果链。可以继续进入费曼解释环节。"
        else:
            content = (
                f"### 诊断结果\n"
                f"**错误原因**：{structured.get('error_reason', '未识别出具体错误原因')}\n\n"
                f"**反馈**：{structured.get('feedback', '')}\n\n"
                f"**缺失概念**：{'、'.join(structured.get('missing_concepts', [])) or '未检测到'}"
            )

        return AgentResult(
            content=content,
            structured_data=structured,
            evidence=evidence,
            confidence=confidence,
            trace=trace,
        )

    # ── Prompt builder ───────────────────────────────────────

    def _build_user_prompt(self, context: AgentContext) -> str:
        """Build the diagnosis user prompt."""
        pre_mapped = context.resources.misconception_data or {}
        questions = context.resources.questions

        question_text = ""
        options_text = ""
        correct_answer = ""
        if questions:
            q = questions[0]
            question_text = q.get("question", "")
            options = q.get("options", {})
            options_text = "\n".join(f"  {k}: {v}" for k, v in options.items())
            correct_answer = q.get("answer", "")

        selected = pre_mapped.get("selected_option", "")
        is_correct = pre_mapped.get("is_correct", False)
        misconception = pre_mapped.get("misconception", "")

        # Format graph context
        graph_context = ""
        if context.resources.graph_nodes:
            node_labels = [
                n.get("label_zh", n.get("id", ""))
                for n in context.resources.graph_nodes[:10]
            ]
            graph_context = "、".join(node_labels)

        return f"""请诊断以下学生的错题。

【题目】
{question_text}

【选项】
{options_text}

【正确答案】
{correct_answer}

【学生选择】
{selected}

【是否正确】
{'正确' if is_correct else '错误'}

{'【预映射的误区】' if misconception else ''}
{misconception}

【相关知识图谱节点】
{graph_context}

{"请分析学生为什么会选错，从因果推理角度找出断裂点。" if not is_correct else "学生答对了，给予简短肯定。"}

请严格按照输出格式返回 JSON。"""

    # ── Trace builder ────────────────────────────────────────

    def _build_reasoning_steps(
        self,
        context: AgentContext,
        pre_mapped: dict,
        structured: dict,
    ) -> list[str]:
        """Build reasoning steps for the trace."""
        question_id = context.metadata.get("question_id", "unknown")
        is_correct = pre_mapped.get("is_correct", False)
        steps = [
            f"诊断题目 {question_id}，学生选项: {pre_mapped.get('selected_option', '?')}",
            f"正确答案: {pre_mapped.get('correct_answer', '?')}，"
            f"学生{'正确' if is_correct else '错误'}",
        ]
        if not is_correct:
            steps.append(f"预映射误区: {pre_mapped.get('misconception', '无')[:80]}")
            if structured.get("ai_enriched"):
                steps.append("LLM 丰富了错误原因和反馈")
            steps.append(
                f"定位缺失概念: {'、'.join(structured.get('missing_concepts', [])) or '无'}"
            )
        return steps
