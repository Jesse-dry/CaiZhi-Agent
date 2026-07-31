"""
Agent layer schemas — AgentContext, AgentResult, AgentEvidence, AgentTrace.

These types define the contract between the Service layer (orchestrator) and
the Agent layer (constrained LLM calls). Every agent receives an AgentContext
with bounded resources and returns an AgentResult with evidence + trace.

Design principles:
  1. Agents are stateless — all state flows through AgentContext → AgentResult
  2. Agents do NOT decide stage transitions — the state machine is the authority
  3. Agents do NOT access Streamlit or FastAPI — they only see bounded data
  4. Evidence + Trace are always populated, even in V1 fallback mode
  5. Structured output varies per agent, but the wrapper (AgentResult) is uniform
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
# AgentResource — bounded data bundle passed to an agent
# ═══════════════════════════════════════════════════════════

class AgentResource(BaseModel):
    """
    Bounded resources an agent is allowed to use.

    Each agent type uses a different subset of these fields.
    The orchestrator (service layer) is responsible for populating only
    the resources the agent is authorized to access.

    Key constraint: agents CANNOT fetch additional data beyond what's
    in this bundle. They reason over the given data only.
    """

    # ── RAG / textbook ──
    rag_chunks: list[dict] = Field(
        default_factory=list,
        description="Retrieved textbook chunks (zh+en) with metadata",
    )
    image_chunks: list[dict] = Field(
        default_factory=list,
        description="Retrieved image caption chunks",
    )

    # ── Knowledge graph ──
    graph_nodes: list[dict] = Field(
        default_factory=list,
        description="Knowledge graph nodes (id, label_zh, label_en, description, term_id)",
    )
    graph_edges: list[dict] = Field(
        default_factory=list,
        description="Knowledge graph edges (source, target, relation)",
    )
    causal_chain: dict | None = Field(
        default=None,
        description="Matched causal chain (chain_id, path[], summary, common_misconceptions)",
    )

    # ── Terminology ──
    terms: list[dict] = Field(
        default_factory=list,
        description="Matched bilingual terminology entries (zh, en, category, definition_zh)",
    )

    # ── Questions / misconceptions ──
    questions: list[dict] = Field(
        default_factory=list,
        description="Relevant self-test questions with options and diagnosis data",
    )
    misconception_data: dict | None = Field(
        default=None,
        description="Pre-mapped misconception diagnosis for a specific question+option",
    )

    # ── Socratic / Feynman ──
    socratic_chain: dict | None = Field(
        default=None,
        description="Socratic teaching chain (socratic_id, title, steps[])",
    )
    feynman_rubric: dict | None = Field(
        default=None,
        description="Feynman evaluation rubric (feynman_id, topic, checklist[], excellent_example)",
    )

    # ── Student history ──
    student_history: list[dict] = Field(
        default_factory=list,
        description="Prior answers/interactions in this session for context",
    )


# ═══════════════════════════════════════════════════════════
# AgentContext — unified input to every agent
# ═══════════════════════════════════════════════════════════

class AgentContext(BaseModel):
    """
    Unified input context for all agents.

    Every agent receives an AgentContext and returns an AgentResult.
    The context carries:
      - Who: session_id for tracing
      - What: student_input (question / answer / explanation)
      - With what: resources (bounded data the agent can use)
      - How: agent_config (temperature, max_tokens, language)
      - Meta: metadata (knowledge_id, chain_id, step_index, attempt_count, etc.)

    Usage:
        ctx = AgentContext(
            session_id="sess_001",
            student_input="为什么淬火能提高硬度？",
            resources=AgentResource(
                rag_chunks=zh_results + en_results,
                causal_chain=graph_chain,
                terms=matched_terms,
            ),
            metadata={"knowledge_id": "K001", "chain_id": "C001"},
        )
        result = await agent.run(ctx)
    """

    session_id: str = Field(..., description="Learning session ID for tracing")
    student_input: str = Field(..., description="Student's question / answer / explanation text", min_length=1)
    resources: AgentResource = Field(
        default_factory=AgentResource,
        description="Bounded data the agent is authorized to use",
    )
    agent_config: dict = Field(
        default_factory=dict,
        description="Optional overrides: temperature, max_tokens, language, model",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Extra context: knowledge_id, chain_id, step_index, attempt_count, question_id, etc.",
    )


# ═══════════════════════════════════════════════════════════
# AgentEvidence — traceable source citations
# ═══════════════════════════════════════════════════════════

class AgentEvidence(BaseModel):
    """
    Evidence trail linking the agent's output back to textbook sources.

    Used for:
      - Displaying "📚 教材依据" in the UI
      - Competition defense: proving the AI didn't hallucinate
      - Debugging: tracing which chunks influenced the output

    Every agent MUST populate this, even in V1 keyword-fallback mode.
    """

    source_chunks: list[str] = Field(
        default_factory=list,
        description="ChromaDB chunk_ids that support the agent's conclusion",
    )
    source_excerpts: list[str] = Field(
        default_factory=list,
        description="Quoted text excerpts from the referenced chunks",
    )
    graph_nodes_used: list[str] = Field(
        default_factory=list,
        description="Knowledge graph node IDs used in the reasoning chain",
    )
    terms_used: list[str] = Field(
        default_factory=list,
        description="Terminology entries referenced (zh term strings)",
    )
    images_used: list[str] = Field(
        default_factory=list,
        description="Image chunk_ids referenced in the answer",
    )

    @property
    def has_evidence(self) -> bool:
        """True if at least one evidence category is non-empty."""
        return bool(
            self.source_chunks
            or self.source_excerpts
            or self.graph_nodes_used
            or self.terms_used
            or self.images_used
        )

    @property
    def summary(self) -> str:
        """Human-readable summary of evidence coverage."""
        parts = []
        if self.source_chunks:
            parts.append(f"{len(self.source_chunks)} textbook chunks")
        if self.graph_nodes_used:
            parts.append(f"{len(self.graph_nodes_used)} graph nodes")
        if self.terms_used:
            parts.append(f"{len(self.terms_used)} terms")
        if self.images_used:
            parts.append(f"{len(self.images_used)} images")
        return ", ".join(parts) if parts else "no evidence"


# ═══════════════════════════════════════════════════════════
# AgentTrace — reasoning trace for explainability
# ═══════════════════════════════════════════════════════════

class AgentTrace(BaseModel):
    """
    Reasoning trace for competition defense and debugging.

    Captures WHY the agent made a specific judgment — the step-by-step
    reasoning, alternatives considered, and decision rationale.

    In V1 keyword-fallback mode, reasoning_steps describe the deterministic
    rule path taken instead of LLM reasoning.
    """

    reasoning_steps: list[str] = Field(
        default_factory=list,
        description="Step-by-step reasoning in natural language",
    )
    decision_rationale: str = Field(
        default="",
        description="Why the agent made this specific judgment / chose this action",
    )
    alternatives_considered: list[str] = Field(
        default_factory=list,
        description="Other options considered and why they were rejected",
    )
    model_name: str = Field(
        default="",
        description="Which LLM model was used (empty for V1 keyword fallback)",
    )
    prompt_version: str = Field(
        default="1.0",
        description="Version tag for the prompt template used",
    )

    @property
    def is_llm_powered(self) -> bool:
        """True if an LLM was used (model_name is non-empty)."""
        return bool(self.model_name)

    def to_display_text(self) -> str:
        """Format the trace as a readable text block for debug UI."""
        lines = [
            f"Model: {self.model_name or 'V1 keyword engine'}",
            f"Prompt version: {self.prompt_version}",
            f"Decision: {self.decision_rationale}" if self.decision_rationale else "",
            "",
        ]
        if self.reasoning_steps:
            lines.append("Reasoning steps:")
            for i, step in enumerate(self.reasoning_steps, 1):
                lines.append(f"  {i}. {step}")
        if self.alternatives_considered:
            lines.append("")
            lines.append("Alternatives considered:")
            for alt in self.alternatives_considered:
                lines.append(f"  • {alt}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# AgentResult — unified output from every agent
# ═══════════════════════════════════════════════════════════

class AgentResult(BaseModel):
    """
    Unified result from any agent.

    Every agent, regardless of its specific task, returns an AgentResult.

    Fields:
      - content: natural language output for display in the UI
      - structured_data: machine-readable structured output (JSON-serializable dict)
        The schema of structured_data varies per agent type:
          * QAAgent: {short_answer, principle, causal_chain, key_terms, ...}
          * DiagnosisAgent: {error_reason, feedback, missing_concepts, ...}
          * SocraticAgent: {quality, covered_points, missing_points, action, response}
          * FeynmanAgent: {dimension_scores, covered_points, missing_points, incorrect_points, ...}
          * GraphReasoningAgent: {missing_prerequisites, recommended_order, causal_gaps}
      - evidence: traceable citations back to textbook sources
      - confidence: 0.0–1.0 confidence score
      - trace: reasoning trace for explainability
    """

    content: str = Field(
        default="",
        description="Natural language output for display in the UI",
    )
    structured_data: dict = Field(
        default_factory=dict,
        description="Machine-readable structured output (schema varies per agent type)",
    )
    evidence: AgentEvidence = Field(
        default_factory=AgentEvidence,
        description="Traceable citations linking output to textbook sources",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score: 0.0 = guess, 1.0 = certain",
    )
    trace: AgentTrace = Field(
        default_factory=AgentTrace,
        description="Reasoning trace for competition defense and debugging",
    )

    @property
    def is_high_confidence(self) -> bool:
        """True if confidence >= 0.8."""
        return self.confidence >= 0.8

    @property
    def needs_review(self) -> bool:
        """True if confidence is low enough to warrant human review."""
        return self.confidence < 0.5


# ═══════════════════════════════════════════════════════════
# Factory helpers
# ═══════════════════════════════════════════════════════════

def create_agent_context(
    session_id: str,
    student_input: str,
    *,
    rag_chunks: list[dict] | None = None,
    image_chunks: list[dict] | None = None,
    graph_nodes: list[dict] | None = None,
    graph_edges: list[dict] | None = None,
    causal_chain: dict | None = None,
    terms: list[dict] | None = None,
    questions: list[dict] | None = None,
    misconception_data: dict | None = None,
    socratic_chain: dict | None = None,
    feynman_rubric: dict | None = None,
    student_history: list[dict] | None = None,
    agent_config: dict | None = None,
    metadata: dict | None = None,
) -> AgentContext:
    """
    Convenience factory for building AgentContext with keyword arguments.

    Usage:
        ctx = create_agent_context(
            session_id="sess_001",
            student_input="为什么淬火能提高硬度？",
            rag_chunks=zh_results + en_results,
            causal_chain=graph_chain,
            terms=matched_terms,
            metadata={"knowledge_id": "K001"},
        )
    """
    return AgentContext(
        session_id=session_id,
        student_input=student_input,
        resources=AgentResource(
            rag_chunks=rag_chunks or [],
            image_chunks=image_chunks or [],
            graph_nodes=graph_nodes or [],
            graph_edges=graph_edges or [],
            causal_chain=causal_chain,
            terms=terms or [],
            questions=questions or [],
            misconception_data=misconception_data,
            socratic_chain=socratic_chain,
            feynman_rubric=feynman_rubric,
            student_history=student_history or [],
        ),
        agent_config=agent_config or {},
        metadata=metadata or {},
    )


def create_v1_agent_result(
    content: str = "",
    structured_data: dict | None = None,
    *,
    source_chunks: list[str] | None = None,
    source_excerpts: list[str] | None = None,
    graph_nodes_used: list[str] | None = None,
    terms_used: list[str] | None = None,
    confidence: float = 0.5,
    reasoning_steps: list[str] | None = None,
    decision_rationale: str = "",
) -> AgentResult:
    """
    Create an AgentResult for V1 keyword-fallback mode.

    In V1 mode, model_name is empty (is_llm_powered = False),
    confidence defaults to 0.5 (rule-based, not AI-assessed),
    and reasoning_steps describe the deterministic rule path.
    """
    return AgentResult(
        content=content,
        structured_data=structured_data or {},
        evidence=AgentEvidence(
            source_chunks=source_chunks or [],
            source_excerpts=source_excerpts or [],
            graph_nodes_used=graph_nodes_used or [],
            terms_used=terms_used or [],
        ),
        confidence=confidence,
        trace=AgentTrace(
            reasoning_steps=reasoning_steps or [],
            decision_rationale=decision_rationale,
            model_name="",  # V1 keyword engine
            prompt_version="1.0",
        ),
    )
