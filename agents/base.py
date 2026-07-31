"""
agents/base.py — BaseAgent Protocol + shared helper utilities.

Every agent implements the BaseAgent Protocol. Shared helpers handle:
  - JSON extraction from LLM responses (_parse_structured_output)
  - System prompt assembly (_build_system_prompt)
  - Evidence cross-referencing (_extract_evidence)
  - Confidence estimation (_estimate_confidence)

Design rules:
  - Agents are stateless: receive AgentContext, return AgentResult
  - Agents never import streamlit or decide stage transitions
  - LLM calls go through infrastructure/llm_client.py
  - Sync LLM calls are wrapped with asyncio.to_thread for async compatibility
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Protocol

from schemas.agent import (
    AgentContext,
    AgentResult,
    AgentEvidence,
    AgentTrace,
    create_v1_agent_result,
)
from infrastructure.llm_client import LLMClient

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# BaseAgent Protocol
# ═══════════════════════════════════════════════════════════

class BaseAgent(Protocol):
    """
    Protocol for all constrained agents.

    Every agent MUST implement:
        async def run(self, context: AgentContext) -> AgentResult: ...

    The agent receives bounded resources in AgentContext, calls the LLM
    (or uses V1 fallback), and returns a structured AgentResult with
    evidence and trace.

    Agents are stateless — they do not hold session state, do not
    access Streamlit, and do not decide learning-stage transitions.

    Usage:
        agent = QAAgent(llm_client)
        result = await agent.run(context)
        # result.content      → display text
        # result.structured_data → machine-readable output
        # result.evidence     → textbook source citations
        # result.trace        → reasoning trace
    """

    async def run(self, context: AgentContext) -> AgentResult:
        """
        Execute the agent's core reasoning.

        Args:
            context: Bounded resources + student input + metadata.

        Returns:
            AgentResult with content, structured_data, evidence, confidence, trace.
        """
        ...


# ═══════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════

# Regex to find the FIRST ```json ... ``` code block in LLM output.
# Handles leading/trailing whitespace and optional language tags.
_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?```",
    re.DOTALL,
)

# Fallback: find the first { ... } JSON object (less reliable).
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_structured_output(
    raw_text: str,
    default: dict | None = None,
) -> dict:
    """
    Extract a JSON dict from an LLM response.

    Tries in order:
      1. ```json ... ``` fenced block
      2. ``` ... ``` fenced block (any language tag)
      3. First { ... } JSON object in the text
      4. Falls back to default (or empty dict)

    Args:
        raw_text: Raw LLM response text.
        default: Fallback value if no valid JSON found.

    Returns:
        Parsed dict.
    """
    if not raw_text:
        return default or {}

    # Strategy 1: ```json / ``` fence
    match = _JSON_FENCE_RE.search(raw_text)
    if match:
        json_str = match.group(1).strip()
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            logger.debug("JSON fence found but invalid JSON, trying next strategy")

    # Strategy 2: bare { ... } object
    match = _JSON_OBJECT_RE.search(raw_text)
    if match:
        json_str = match.group(0)
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            logger.debug("JSON object found but invalid JSON, returning default")

    # Strategy 3: return default
    logger.warning(
        "Could not extract valid JSON from LLM response "
        f"(length={len(raw_text)}), returning default"
    )
    return default or {}


def _build_system_prompt(
    role: str,
    constraints: list[str] | None = None,
    output_format: dict[str, str] | None = None,
    extra_instructions: str = "",
) -> str:
    """
    Assemble a structured system prompt with 4 sections:
      [ROLE] [CONSTRAINTS] [OUTPUT FORMAT] [EXTRA]

    Args:
        role: Agent identity and core responsibility.
        constraints: List of "MUST" / "MUST NOT" rules.
        output_format: Dict mapping field_name → description for the JSON output.
        extra_instructions: Additional instructions appended at end.

    Returns:
        Assembled system prompt string.
    """
    sections = [f"## 角色\n{role}"]

    if constraints:
        lines = "\n".join(f"- {c}" for c in constraints)
        sections.append(f"## 约束\n{lines}")

    if output_format:
        lines = "\n".join(f'  "{k}": {v}' for k, v in output_format.items())
        sections.append(
            f"## 输出格式\n返回一个 JSON 对象，用 ```json ``` 包裹：\n{{\n{lines}\n}}"
        )

    if extra_instructions:
        sections.append(f"## 补充说明\n{extra_instructions}")

    return "\n\n".join(sections)


def _extract_evidence(
    structured_data: dict,
    resources_rag_chunks: list[dict],
    resources_terms: list[dict],
    resources_graph_nodes: list[dict],
    max_excerpts: int = 5,
) -> AgentEvidence:
    """
    Cross-reference structured output claims with provided resource chunks.

    Strategy (heuristic, not LLM):
      - For each text value in structured_data, check if it appears
        as a substring of any provided chunk's text
      - Terms used: check if term strings appear in structured_data values
      - Graph nodes: check if node IDs or labels appear

    This is a deterministic V1 approximation. In V2, the LLM could
    self-report which chunks it used.

    Args:
        structured_data: The parsed structured output from the agent.
        resources_rag_chunks: The RAG chunks provided to the agent.
        resources_terms: The terminology entries provided.
        resources_graph_nodes: The graph nodes provided.
        max_excerpts: Max number of excerpts to include.

    Returns:
        AgentEvidence with cross-referenced sources.
    """
    # Flatten all text values from structured_data for matching
    all_values = " ".join(
        str(v) for v in structured_data.values()
        if isinstance(v, (str, list))
    ).lower()

    # Match RAG chunks
    source_chunks: list[str] = []
    source_excerpts: list[str] = []
    for chunk in resources_rag_chunks:
        chunk_id = _get_chunk_id(chunk)
        chunk_text = (chunk.get("text", "") or "").lower()
        if chunk_text and len(chunk_text) > 30 and chunk_text[:100] in all_values:
            if chunk_id:
                source_chunks.append(chunk_id)
            if len(source_excerpts) < max_excerpts:
                excerpt = (chunk.get("text", "") or "")[:200]
                if excerpt:
                    source_excerpts.append(excerpt)

    # Match terms
    terms_used: list[str] = []
    for term in resources_terms:
        zh = term.get("zh", "")
        en = term.get("en", "")
        if (zh and zh in all_values) or (en and en.lower() in all_values):
            terms_used.append(zh or en)

    # Match graph nodes
    graph_nodes_used: list[str] = []
    for node in resources_graph_nodes:
        node_id = node.get("id", "")
        label_zh = node.get("label_zh", "")
        if node_id and (node_id.lower() in all_values or label_zh in all_values):
            graph_nodes_used.append(node_id)

    return AgentEvidence(
        source_chunks=source_chunks,
        source_excerpts=source_excerpts,
        graph_nodes_used=graph_nodes_used,
        terms_used=terms_used,
    )


def _get_chunk_id(chunk: dict) -> str:
    """Extract chunk_id from a RAG result dict (handles varying key locations)."""
    meta = chunk.get("metadata", {})
    return meta.get("chunk_id", "") or chunk.get("chunk_id", "") or chunk.get("id", "")


def _estimate_confidence(
    structured_data: dict,
    has_llm: bool,
) -> float:
    """
    Heuristic confidence estimation.

    V1 keyword: fixed 0.5
    V2 LLM: based on structured_data completeness (all expected keys present?)

    Individual agents can override this with domain-specific logic.
    """
    if not has_llm:
        return 0.5

    # Simple heuristic: more populated fields → higher confidence
    if not structured_data:
        return 0.3

    populated = sum(
        1 for v in structured_data.values()
        if v is not None and v != "" and v != []
    )
    total = len(structured_data)
    if total == 0:
        return 0.3

    ratio = populated / total
    return round(min(0.95, max(0.3, ratio)), 2)


# ═══════════════════════════════════════════════════════════
# LLM call wrapper — sync → async
# ═══════════════════════════════════════════════════════════

async def _call_llm(
    llm_client: LLMClient,
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """
    Call the LLM client synchronously via asyncio.to_thread.

    The LLMClient.chat() is synchronous (blocking HTTP call).
    We wrap it with to_thread to avoid blocking the event loop,
    following the pattern in llm_client._chat_openai_compatible_stream.

    Args:
        llm_client: The LLM client instance.
        system_prompt: System-level instructions.
        user_prompt: The user message (data + task).
        temperature: Override default temperature.
        max_tokens: Override default max_tokens.

    Returns:
        LLM response text (empty string on failure).
    """
    try:
        result = await asyncio.to_thread(
            llm_client.chat,
            prompt=user_prompt,
            system=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return result or ""
    except Exception as e:
        logger.error(f"LLM call failed: {type(e).__name__}: {e}")
        return ""
