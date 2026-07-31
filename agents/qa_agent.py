"""
agents/qa_agent.py — QAAgent: 基于教材的智能答疑。

Constrained agent: receives RAG chunks + causal chain + terms →
builds a constrained prompt → calls LLM → parses structured JSON output.

Replaces: QAService placeholder short_answer/principle (currently graph summaries).
V1 fallback: returns graph chain summary as content.

Design:
  - Uses knowledge/prompt_builder.py build_constrained_qa_prompt() approach
  - System prompt enforces 4-source boundary (RAG/graph/terms/questions)
  - Structured output: short_answer, principle, causal_chain, key_terms, misconceptions
"""

from __future__ import annotations

import logging

from schemas.agent import AgentContext, AgentResult, AgentEvidence, AgentTrace
from agents.base import (
    _parse_structured_output,
    _build_system_prompt,
    _extract_evidence,
    _call_llm,
    _estimate_confidence,
)
from infrastructure.llm_client import LLMClient

logger = logging.getLogger(__name__)

QA_PROMPT_VERSION = "1.0"

# ── System prompt sections ──

QA_ROLE = """你是《材料科学与工程》专业的 AI 助教（材智 Agent）。
你的职责是基于教材内容回答学生的问题。
你必须严格依据提供的教材片段、知识图谱和术语表来作答，
不得使用外部知识或编造教材中不存在的内容。
如果教材没有覆盖某个知识点，要诚实地说"当前教材依据不足"。
使用中文回答。"""

QA_CONSTRAINTS = [
    "必须引用教材片段作为事实依据（RAG chunks），不得凭空编造",
    "因果链必须使用提供的知识图谱路径，不得自行编造节点",
    "术语的中英文翻译必须与提供的术语表一致，不得自己翻译",
    "推荐的自测题必须是提供的题目之一，不得临时编造新题",
    "如果教材片段不足以回答问题，必须明确指出",
    "回答结构必须包含：简明回答、原理、因果链、术语、教材依据、误区、自测题",
]

QA_OUTPUT_FORMAT = {
    "short_answer": "2-3句话直接回答问题",
    "principle": "按'工艺→组织→结构→性能'展开的原理解释，200-400字",
    "causal_chain": "因果链步骤列表，每步包含 node_id, label_zh, relation, explanation",
    "key_terms": "关键术语列表，每项包含 zh, en, category, definition_zh",
    "misconceptions": "常见误区提示列表（字符串数组）",
    "self_test_question": "推荐的自测题（question_id + question 文本）",
    "textbook_sources": "引用的教材来源列表，每项包含 file_name, chapter, excerpt",
    "confidence": "你对本次回答的信心程度，0.0-1.0",
}


# ═══════════════════════════════════════════════════════════
# QAAgent
# ═══════════════════════════════════════════════════════════

class QAAgent:
    """
    智能答疑 Agent — 基于教材内容回答问题。

    可调用资源：RAG 教材片段、术语表、知识图谱、题库
    不可做：编造教材外内容、自己翻译术语、临时出题

    Usage:
        agent = QAAgent(llm_client)
        result = await agent.run(context)
        # result.structured_data["short_answer"] → LLM 生成的简明回答
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def run(self, context: AgentContext) -> AgentResult:
        """
        执行智能答疑。

        Args:
            context: AgentContext with student_input (question) + resources.

        Returns:
            AgentResult with LLM-generated answer + evidence + trace.
        """
        # 1. Build prompts
        system_prompt = _build_system_prompt(
            role=QA_ROLE,
            constraints=QA_CONSTRAINTS,
            output_format=QA_OUTPUT_FORMAT,
        )
        user_prompt = self._build_user_prompt(context)

        # 2. Call LLM
        temperature = context.agent_config.get("temperature", 0.3)
        max_tokens = context.agent_config.get("max_tokens", 2048)

        raw_response = await _call_llm(
            self.llm,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # 3. Parse structured output
        if raw_response:
            structured = _parse_structured_output(raw_response)
            llm_confidence = structured.pop("confidence", None)
            confidence = (
                float(llm_confidence)
                if llm_confidence is not None
                else _estimate_confidence(structured, has_llm=True)
            )
        else:
            structured = self._v1_fallback(context)
            confidence = 0.5
            raw_response = ""

        # 4. Build evidence
        evidence = _extract_evidence(
            structured_data=structured,
            resources_rag_chunks=context.resources.rag_chunks,
            resources_terms=context.resources.terms,
            resources_graph_nodes=context.resources.graph_nodes,
        )

        # 5. Build trace
        trace = AgentTrace(
            reasoning_steps=self._build_reasoning_steps(context, structured),
            decision_rationale=(
                f"基于 {len(context.resources.rag_chunks)} 个教材片段"
                f"和知识图谱因果链生成回答"
            ),
            alternatives_considered=[
                "仅用知识图谱摘要" if not raw_response else "完整 LLM 生成"
            ],
            model_name=self.llm.config.model if raw_response else "",
            prompt_version=QA_PROMPT_VERSION,
        )

        # 6. Build display content
        content = self._build_content(structured)

        return AgentResult(
            content=content,
            structured_data=structured,
            evidence=evidence,
            confidence=confidence,
            trace=trace,
        )

    # ── V1 fallback ──────────────────────────────────────────

    def _v1_fallback(self, context: AgentContext) -> dict:
        """Return graph chain summary as V1 placeholder."""
        chain = context.resources.causal_chain
        summary = chain.get("summary", "") if chain else ""
        chain_path = chain.get("path", []) if chain else []

        return {
            "short_answer": summary or "当前教材依据不足，无法给出确切回答。",
            "principle": summary or "",
            "causal_chain": [
                {"node_id": n, "label_zh": n, "relation": "", "explanation": ""}
                for n in chain_path
            ],
            "key_terms": context.resources.terms[:6] if context.resources.terms else [],
            "misconceptions": (
                chain.get("common_misconceptions", []) if chain else []
            ),
            "self_test_question": "",
            "textbook_sources": [],
        }

    # ── Prompt builders ──────────────────────────────────────

    def _build_user_prompt(self, context: AgentContext) -> str:
        """Build the constrained QA user prompt from AgentContext resources."""
        from knowledge.prompt_builder import (
            _fmt_contexts,
            _fmt_terms,
            _fmt_causal_chain,
            _fmt_misconceptions,
            _fmt_self_test,
            _fmt_sources,
        )

        resources = context.resources

        zh_chunks = [
            c for c in resources.rag_chunks
            if (c.get("metadata", {}) if isinstance(c, dict) else {}).get("language") == "zh"
        ]
        en_chunks = [
            c for c in resources.rag_chunks
            if (c.get("metadata", {}) if isinstance(c, dict) else {}).get("language") == "en"
        ]

        chain_path = resources.causal_chain.get("path", []) if resources.causal_chain else []

        misconceptions = (
            resources.causal_chain.get("common_misconceptions", [])
            if resources.causal_chain else []
        )

        self_test = None
        if resources.questions:
            q = resources.questions[0]
            self_test = {
                "question": q.get("question", ""),
                "question_id": q.get("question_id", ""),
            }

        prompt = f"""请根据以下数据回答学生问题。

══════════════════════════════════════
【数据】
══════════════════════════════════════

【学生问题】
{context.student_input}

【中文教材片段】
{_fmt_contexts(zh_chunks, "中文教材")}

【英文教材片段】
{_fmt_contexts(en_chunks, "English Textbook")}

【图表描述】
{_fmt_contexts(resources.image_chunks, "图表描述", max_items=3)}

【知识图谱因果链】
{_fmt_causal_chain(chain_path)}

【标准术语表】
{_fmt_terms(resources.terms)}

【常见误区】
{_fmt_misconceptions(misconceptions)}

【匹配的自测题】
{_fmt_self_test(self_test)}

【教材来源】
{_fmt_sources(self._build_source_list(resources.rag_chunks))}

请严格按照输出格式返回 JSON。"""
        return prompt

    def _build_source_list(self, rag_chunks: list[dict], max_sources: int = 10) -> list[dict]:
        """Build a human-readable source list from RAG chunks."""
        sources: list[dict] = []
        seen: set[str] = set()
        for item in rag_chunks:
            if not isinstance(item, dict):
                continue
            meta = item.get("metadata", {})
            chunk_id = meta.get("chunk_id", "")
            if not chunk_id or chunk_id in seen:
                continue
            seen.add(chunk_id)
            sources.append({
                "chunk_id": chunk_id,
                "file_name": meta.get("file_name", ""),
                "language": meta.get("language", ""),
                "chapter": meta.get("chapter", ""),
                "page": meta.get("page"),
                "text": (item.get("text", "") or "")[:300],
            })
            if len(sources) >= max_sources:
                break
        return sources

    # ── Output builders ──────────────────────────────────────

    def _build_content(self, structured: dict) -> str:
        """Build a display-friendly markdown string from structured output."""
        parts = []

        if structured.get("short_answer"):
            parts.append(f"### 简明回答\n{structured['short_answer']}")

        if structured.get("principle"):
            parts.append(f"### 材料学原理\n{structured['principle']}")

        if structured.get("causal_chain"):
            parts.append("### 因果链")
            for step in structured["causal_chain"]:
                if isinstance(step, dict):
                    label = step.get("label_zh", step.get("node_id", "?"))
                    relation = step.get("relation", "")
                    suffix = f"（{relation}）" if relation else ""
                    parts.append(f"- {label}{suffix}")

        if structured.get("key_terms"):
            parts.append("### 关键术语")
            for t in structured["key_terms"]:
                if isinstance(t, dict):
                    zh = t.get("zh", "")
                    en = t.get("en", "")
                    parts.append(f"- {zh}" + (f" / {en}" if en else ""))

        if structured.get("misconceptions"):
            parts.append("### 常见误区")
            for m in structured["misconceptions"]:
                parts.append(f"- {m}")

        return "\n\n".join(parts) if parts else structured.get("short_answer", "")

    def _build_reasoning_steps(
        self, context: AgentContext, structured: dict
    ) -> list[str]:
        """Build human-readable reasoning steps for the trace."""
        steps = [
            f"接收到学生问题: {context.student_input[:100]}",
            f"检索到 {len(context.resources.rag_chunks)} 个教材片段（zh+en）",
        ]
        if context.resources.causal_chain:
            chain_id = context.resources.causal_chain.get("chain_id", "unknown")
            path_len = len(context.resources.causal_chain.get("path", []))
            steps.append(f"匹配到因果链 {chain_id}（{path_len} 个节点）")
        if context.resources.terms:
            steps.append(f"匹配到 {len(context.resources.terms)} 个相关术语")
        if structured:
            steps.append(f"生成结构化回答，包含 {len(structured)} 个字段")
        return steps
