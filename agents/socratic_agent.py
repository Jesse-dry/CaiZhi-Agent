"""
agents/socratic_agent.py — SocraticAgent: 判断回答并选择下一步提示。

Constrained agent: receives socratic step + student answer + attempt count →
judges quality → decides action (advance/hint/retry/simplify).

Replaces: socratic_service.judge_answer() keyword matching.
V1 fallback: keyword-based matching (kept for offline/error cases).

Design:
  - System prompt enforces Socratic method: never reveal the answer directly
  - Structured output: quality, covered_points, missing_points, action, response
  - Actions follow the existing SocraticAction enum: advance/hint/retry/simplify/complete
"""

from __future__ import annotations

import logging

from schemas.agent import AgentContext, AgentResult, AgentTrace
from schemas.common import AnswerQuality, SocraticAction
from agents.base import (
    _parse_structured_output,
    _build_system_prompt,
    _call_llm,
)
from infrastructure.llm_client import LLMClient

logger = logging.getLogger(__name__)

SOCRATIC_PROMPT_VERSION = "1.0"

# ── System prompt sections ──

SOCRATIC_ROLE = """你是《材料科学与工程》专业的苏格拉底式导师（材智 Agent）。
你的职责是通过提问引导学生自己发现答案，而不是直接告诉学生答案。
你要判断学生的回答覆盖了哪些概念、缺失了哪些概念，
然后决定下一步：推进到下一个问题（advance）、给提示（hint）、
让重试（retry），还是简化问题（simplify）。

核心原则：永远不直接说出最终答案，只给引导性提示。"""

SOCRATIC_CONSTRAINTS = [
    "永远不直接说出最终答案，只给引导性提示",
    "判断学生的回答是否覆盖了期望的知识点",
    "根据尝试次数调整策略：第1-2次给提示，第3次以上简化问题",
    "用鼓励的语气，先肯定学生已有的理解，再指出缺失",
    "提示要具体，不能是'再想想'这种空话",
    "用中文回答",
]

SOCRATIC_OUTPUT_FORMAT = {
    "quality": "回答质量：complete / partial / incorrect",
    "covered_points": "学生已覆盖的知识点列表（字符串数组）",
    "missing_points": "学生缺失的知识点列表（字符串数组）",
    "action": "系统动作：advance / hint / retry / simplify / complete",
    "response": "给学生的反馈文本（2-4句话，鼓励+引导）",
    "confidence": "判断信心程度，0.0-1.0",
}


# ═══════════════════════════════════════════════════════════
# Action validation
# ═══════════════════════════════════════════════════════════

VALID_ACTIONS = {a.value for a in SocraticAction}
VALID_QUALITIES = {q.value for q in AnswerQuality}


def _validate_action(raw: str) -> str:
    """Normalize LLM output action to a valid SocraticAction value."""
    raw = raw.strip().lower()
    if raw in VALID_ACTIONS:
        return raw
    # Fuzzy mapping
    mapping = {
        "advance": "advance", "next": "advance", "continue": "advance",
        "hint": "hint", "clue": "hint", "tip": "hint",
        "retry": "retry", "again": "retry", "redo": "retry",
        "simplify": "simplify", "simple": "simplify", "easier": "simplify",
        "complete": "complete", "done": "complete", "finish": "complete",
    }
    return mapping.get(raw, "hint")


def _validate_quality(raw: str) -> str:
    """Normalize LLM output quality to a valid AnswerQuality value."""
    raw = raw.strip().lower()
    if raw in VALID_QUALITIES:
        return raw
    mapping = {
        "complete": "complete", "full": "complete", "correct": "complete",
        "partial": "partial", "partly": "partial", "some": "partial",
        "incorrect": "incorrect", "wrong": "incorrect", "none": "incorrect",
    }
    return mapping.get(raw, "partial")


# ═══════════════════════════════════════════════════════════
# SocraticAgent
# ═══════════════════════════════════════════════════════════

class SocraticAgent:
    """
    苏格拉底引导 Agent — 判断回答并选择下一步提示。

    可调用资源：苏格拉底教学链
    不可做：直接告诉答案、自己编造教学步骤

    Usage:
        agent = SocraticAgent(llm_client)
        result = await agent.run(context)
        # result.structured_data["action"] → "advance" | "hint" | "retry" | "simplify"
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def run(self, context: AgentContext) -> AgentResult:
        """
        判断学生回答质量并决定下一步动作。

        Args:
            context: AgentContext with:
                - student_input: student's answer
                - resources.socratic_chain: full chain context
                - metadata.step_index, metadata.attempt_count

        Returns:
            AgentResult with quality judgment + action decision.
        """
        # 1. Build prompts
        system_prompt = _build_system_prompt(
            role=SOCRATIC_ROLE,
            constraints=SOCRATIC_CONSTRAINTS,
            output_format=SOCRATIC_OUTPUT_FORMAT,
        )
        user_prompt = self._build_user_prompt(context)

        # 2. Call LLM
        raw_response = await _call_llm(
            self.llm,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.4,
            max_tokens=1024,
        )

        # 3. Parse structured output
        if raw_response:
            structured = _parse_structured_output(raw_response)
            structured["action"] = _validate_action(structured.get("action", "hint"))
            structured["quality"] = _validate_quality(structured.get("quality", "partial"))
            confidence = float(structured.pop("confidence", 0.6))
        else:
            structured = self._v1_fallback(context)
            confidence = 0.5

        # 4. Build evidence (lightweight — socratic uses chain steps, not RAG)
        evidence = self._build_evidence(context, structured)

        # 5. Build trace
        trace = AgentTrace(
            reasoning_steps=self._build_reasoning_steps(context, structured),
            decision_rationale=(
                f"学生回答质量: {structured.get('quality', '?')}, "
                f"动作: {structured.get('action', '?')}, "
                f"第 {context.metadata.get('attempt_count', 1)} 次尝试"
            ),
            alternatives_considered=self._alternatives_for_action(
                structured.get("action", "hint")
            ),
            model_name=self.llm.config.model if raw_response else "",
            prompt_version=SOCRATIC_PROMPT_VERSION,
        )

        return AgentResult(
            content=structured.get("response", ""),
            structured_data=structured,
            evidence=evidence,
            confidence=confidence,
            trace=trace,
        )

    # ── V1 fallback (keyword matching) ───────────────────────

    def _v1_fallback(self, context: AgentContext) -> dict:
        """Keyword-based fallback, mirrors V1 socratic_service logic."""
        chain = context.resources.socratic_chain or {}
        steps = chain.get("steps", [])
        step_idx = context.metadata.get("step_index", 1)
        attempt = context.metadata.get("attempt_count", 1)

        # Find current step
        current_step = None
        for s in steps:
            if s.get("step") == step_idx:
                current_step = s
                break

        if not current_step:
            return {
                "quality": "partial",
                "covered_points": [],
                "missing_points": [],
                "action": "advance",
                "response": "继续下一步。",
            }

        expected = current_step.get("expected_keywords", [])
        answer_lower = context.student_input.lower()
        covered = [kw for kw in expected if kw.lower() in answer_lower]
        missing = [kw for kw in expected if kw.lower() not in answer_lower]

        total = len(expected)
        matched = len(covered)
        ratio = matched / total if total > 0 else 0

        if ratio >= 0.75:
            quality, action = "complete", "advance"
            response = f"很好！你已经提到了：{'、'.join(covered)}。我们继续下一步。"
        elif ratio > 0:
            quality = "partial"
            if attempt >= 3:
                action = "simplify"
                response = f"我们换个方式理解。{'、'.join(missing)}：{current_step.get('explanation_if_wrong', '')}"
            else:
                action = "hint"
                hint = current_step.get("hint", "")
                response = f"你已经想到了：{'、'.join(covered)}。再想想：{'、'.join(missing)}？"
                if hint:
                    response += f"\n\n💡 {hint}"
        else:
            quality = "incorrect"
            if attempt >= 3:
                action = "simplify"
                response = f"我们换个方式理解：{current_step.get('explanation_if_wrong', '')}"
            else:
                action = "retry"
                response = f"还不太对。{current_step.get('explanation_if_wrong', '')}\n\n请再试一次。"

        return {
            "quality": quality,
            "covered_points": covered,
            "missing_points": missing,
            "action": action,
            "response": response,
        }

    # ── Prompt builder ───────────────────────────────────────

    def _build_user_prompt(self, context: AgentContext) -> str:
        """Build the socratic judgment prompt."""
        chain = context.resources.socratic_chain or {}
        steps = chain.get("steps", [])
        step_idx = context.metadata.get("step_index", 1)
        attempt = context.metadata.get("attempt_count", 1)

        current_step = None
        all_steps_text = ""
        for i, s in enumerate(steps):
            sq = s.get("question", "")
            all_steps_text += f"  步骤{i + 1}: {sq}\n"
            if s.get("step") == step_idx:
                current_step = s

        if not current_step:
            current_step = {}

        expected = current_step.get("expected_keywords", [])
        hint = current_step.get("hint", "")
        explanation = current_step.get("explanation_if_wrong", "")

        return f"""请判断学生的回答并决定下一步。

【完整教学链】
{all_steps_text}

【当前步骤】（第 {step_idx} 步，第 {attempt} 次尝试）
问题: {current_step.get('question', '')}
期望知识点: {'、'.join(expected)}
{'提示: ' + hint if hint else ''}
{'解释（错误时用）: ' + explanation if explanation else ''}

【学生回答】
{context.student_input}

【判断指南】
- 如果学生覆盖了 >= 75% 的期望知识点 → advance
- 如果学生覆盖了部分但不足 75% 且尝试 < 3 → hint
- 如果学生完全没覆盖且尝试 < 3 → retry
- 如果尝试 >= 3 次仍未达标 → simplify

请严格按照输出格式返回 JSON。"""

    # ── Evidence & trace ─────────────────────────────────────

    def _build_evidence(self, context: AgentContext, structured: dict) -> "AgentEvidence":
        """Build lightweight evidence from socratic chain context."""
        from schemas.agent import AgentEvidence

        chain = context.resources.socratic_chain or {}
        terms_used = list(set(structured.get("covered_points", []) + structured.get("missing_points", [])))

        return AgentEvidence(
            source_chunks=[],
            source_excerpts=[],
            graph_nodes_used=[],
            terms_used=terms_used,
        )

    def _build_reasoning_steps(
        self, context: AgentContext, structured: dict
    ) -> list[str]:
        """Build reasoning steps for the trace."""
        step_idx = context.metadata.get("step_index", 1)
        attempt = context.metadata.get("attempt_count", 1)

        steps = [
            f"苏格拉底引导第 {step_idx} 步，第 {attempt} 次尝试",
            f"已覆盖知识点: {'、'.join(structured.get('covered_points', [])) or '无'}",
            f"缺失知识点: {'、'.join(structured.get('missing_points', [])) or '无'}",
            f"动作决策: {structured.get('action', '?')}",
        ]
        return steps

    def _alternatives_for_action(self, action: str) -> list[str]:
        """Describe rejected alternatives for trace transparency."""
        all_actions = ["advance", "hint", "retry", "simplify"]
        others = [a for a in all_actions if a != action]
        return [f"考虑过 {a} 但基于学生回答选择了 {action}" for a in others]
