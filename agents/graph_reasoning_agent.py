"""
agents/graph_reasoning_agent.py — GraphReasoningAgent: 缺失因果链和先修节点推理。

Constrained agent: receives knowledge graph (nodes + edges) + student weak points →
identifies missing prerequisite nodes, causal gaps, and optimal learning order.

Replaces: recommendation_service keyword-based unit mapping + prerequisite sort.
Key improvement: LLM can identify causal gaps that keyword matching misses,
and reason about which prerequisite concepts the student is missing.

Design:
  - System prompt focuses on graph topology reasoning
  - Structured output: missing_prerequisites, recommended_order, causal_gaps
  - V1 fallback: keyword-based mapping + topological sort (existing logic)
"""

from __future__ import annotations

import logging

from schemas.agent import AgentContext, AgentResult, AgentTrace
from agents.base import (
    _parse_structured_output,
    _build_system_prompt,
    _call_llm,
)
from infrastructure.llm_client import LLMClient

logger = logging.getLogger(__name__)

GRAPH_REASONING_PROMPT_VERSION = "1.0"

# ── System prompt sections ──

GRAPH_ROLE = """你是《材料科学与工程》专业的知识图谱推理专家（材智 Agent）。
你的职责是分析知识图谱中节点之间的因果和先修关系，
根据学生当前的薄弱点，推理出学生可能缺失的先修知识，
并给出最优的学习顺序。

你需要理解材料科学的因果逻辑：
工艺（如淬火）→ 组织（如马氏体）→ 结构/缺陷（如晶格畸变）→ 性能（如硬度提高）"""

GRAPH_CONSTRAINTS = [
    "只能使用提供的知识图谱节点和边来推理，不得编造新节点",
    "推理要基于图拓扑：如果一个节点有先修依赖而学生缺失，就标记为 missing_prerequisite",
    "推荐的路径必须遵循先修关系（prerequisites 边）",
    "用中文回答",
]

GRAPH_OUTPUT_FORMAT = {
    "missing_prerequisites": "学生可能缺失的先修节点列表（node_id 数组）",
    "recommended_order": "推荐的学习节点顺序（node_id 数组，按先修依赖排序）",
    "causal_gaps": "因果推理链中的断裂描述列表（字符串数组，每个描述一个断裂点）",
    "reasoning": "推理过程简述（1-2句话）",
    "confidence": "推理信心程度，0.0-1.0",
}


# ═══════════════════════════════════════════════════════════
# GraphReasoningAgent
# ═══════════════════════════════════════════════════════════

class GraphReasoningAgent:
    """
    知识图谱推理 Agent — 找到缺失因果链和先修节点。

    可调用资源：知识图谱（nodes + edges + causal_chains）
    不可做：编造图谱之外的节点或关系

    Usage:
        agent = GraphReasoningAgent(llm_client)
        result = await agent.run(context)
        # result.structured_data["missing_prerequisites"] → ["K002", "K004"]
        # result.structured_data["causal_gaps"] → ["学生理解奥氏体→马氏体转变，但不知道晶格畸变的后果"]
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def run(self, context: AgentContext) -> AgentResult:
        """
        推理知识图谱中的缺失路径。

        Args:
            context: AgentContext with:
                - student_input / metadata.weak_points: student's weak areas
                - resources.graph_nodes: all KG nodes
                - resources.graph_edges: all KG edges
                - resources.causal_chain: matched causal chain

        Returns:
            AgentResult with prerequisite gaps + learning order.
        """
        # 1. Build prompts
        system_prompt = _build_system_prompt(
            role=GRAPH_ROLE,
            constraints=GRAPH_CONSTRAINTS,
            output_format=GRAPH_OUTPUT_FORMAT,
        )
        user_prompt = self._build_user_prompt(context)

        # 2. Call LLM
        raw_response = await _call_llm(
            self.llm,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.2,  # Low temperature for graph reasoning
            max_tokens=1024,
        )

        # 3. Parse structured output
        if raw_response:
            structured = _parse_structured_output(raw_response)
            confidence = float(structured.pop("confidence", 0.7))
        else:
            structured = self._v1_fallback(context)
            confidence = 0.5

        # 4. Build evidence (graph-based, not RAG)
        evidence = self._build_evidence(context, structured)

        # 5. Build trace
        trace = AgentTrace(
            reasoning_steps=self._build_reasoning_steps(context, structured),
            decision_rationale=structured.get("reasoning", "基于知识图谱拓扑分析"),
            alternatives_considered=["纯关键词映射" if raw_response else "尝试 LLM 推理但失败"],
            model_name=self.llm.config.model if raw_response else "",
            prompt_version=GRAPH_REASONING_PROMPT_VERSION,
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
        """Topological sort based on prerequisite edges (keyword-free)."""
        nodes = context.resources.graph_nodes
        edges = context.resources.graph_edges

        # Build adjacency
        node_ids = {n.get("id", "") for n in nodes if n.get("id")}
        prereq_map: dict[str, set[str]] = {}
        for e in edges:
            src = e.get("source", "")
            tgt = e.get("target", "")
            # "requires" edges: target requires source (source is prerequisite)
            if e.get("relation") in ("requires", "prerequisite"):
                if tgt not in prereq_map:
                    prereq_map[tgt] = set()
                prereq_map[tgt].add(src)

        # Identify weak areas from metadata
        weak_points = context.metadata.get("weak_points", [])
        if not weak_points and context.student_input:
            weak_points = [context.student_input]

        # All node IDs as recommended order (topological by prereq count)
        ordered = sorted(
            node_ids,
            key=lambda nid: len(prereq_map.get(nid, set())),
        )

        # Missing prerequisites: for each node in weak area, find unvisited prereqs
        missing: list[str] = []
        for nid in list(node_ids)[:5]:
            prereqs = prereq_map.get(nid, set())
            for p in prereqs:
                if p not in ordered[:ordered.index(nid)] if nid in ordered else True:
                    if p not in missing:
                        missing.append(p)

        return {
            "missing_prerequisites": missing[:5],
            "recommended_order": ordered[:8],
            "causal_gaps": [],
            "reasoning": "基于知识图谱先修边（prerequisite edges）的拓扑排序",
        }

    # ── Prompt builder ───────────────────────────────────────

    def _build_user_prompt(self, context: AgentContext) -> str:
        """Build the graph reasoning prompt."""
        nodes = context.resources.graph_nodes
        edges = context.resources.graph_edges

        # Format nodes
        nodes_text = ""
        for n in nodes[:20]:
            nid = n.get("id", "")
            label = n.get("label_zh", nid)
            desc = n.get("description", "")
            nodes_text += f"  {nid}: {label}"
            if desc:
                nodes_text += f" — {desc[:80]}"
            nodes_text += "\n"

        # Format edges
        edges_text = ""
        for e in edges[:30]:
            src = e.get("source", "")
            tgt = e.get("target", "")
            rel = e.get("relation", "")
            edges_text += f"  {src} --[{rel}]--> {tgt}\n"

        # Weak points from metadata or student_input
        weak_points = context.metadata.get("weak_points", [])
        if not weak_points:
            weak_points = [context.student_input] if context.student_input else ["淬火"]

        # Causal chain context
        chain_text = ""
        if context.resources.causal_chain:
            chain = context.resources.causal_chain
            chain_text = f"因果链 {chain.get('chain_id', '')}: {' → '.join(chain.get('path', []))}"

        return f"""请分析以下知识图谱，找出学生的知识盲区。

【知识图谱节点】
{nodes_text}

【知识图谱边】
{edges_text}

【因果链】
{chain_text}

【学生薄弱点】
{'、'.join(weak_points)}

请推理：
1. 学生在因果链的哪个位置可能断裂？（causal_gaps）
2. 缺失了哪些先修节点？（missing_prerequisites）
3. 推荐什么学习顺序？（recommended_order，按先修依赖排列）

请严格按照输出格式返回 JSON。"""

    # ── Evidence & trace ─────────────────────────────────────

    def _build_evidence(self, context: AgentContext, structured: dict) -> "AgentEvidence":
        """Build evidence from graph nodes used."""
        from schemas.agent import AgentEvidence

        return AgentEvidence(
            source_chunks=[],
            source_excerpts=[],
            graph_nodes_used=list(set(
                structured.get("missing_prerequisites", [])
                + structured.get("recommended_order", [])
            )),
            terms_used=[],
        )

    def _build_reasoning_steps(
        self, context: AgentContext, structured: dict
    ) -> list[str]:
        """Build reasoning steps for the trace."""
        steps = [
            f"知识图谱: {len(context.resources.graph_nodes)} 个节点, "
            f"{len(context.resources.graph_edges)} 条边",
            f"缺失先修节点: {'、'.join(structured.get('missing_prerequisites', [])) or '无'}",
            f"因果断裂: {'、'.join(structured.get('causal_gaps', [])) or '未检测到'}",
            f"推荐学习顺序: {' → '.join(structured.get('recommended_order', [])[:5])}",
        ]
        return steps

    def _build_content(self, structured: dict) -> str:
        """Build display-friendly markdown."""
        parts = []

        if structured.get("missing_prerequisites"):
            parts.append("### 缺失的先修知识")
            for p in structured["missing_prerequisites"]:
                parts.append(f"- {p}")

        if structured.get("causal_gaps"):
            parts.append("### 因果推理断裂点")
            for g in structured["causal_gaps"]:
                parts.append(f"- {g}")

        if structured.get("recommended_order"):
            parts.append("### 推荐学习路径")
            parts.append(" → ".join(structured["recommended_order"]))

        if structured.get("reasoning"):
            parts.append(f"\n*{structured['reasoning']}*")

        return "\n".join(parts) if parts else "无法生成推荐路径。"
