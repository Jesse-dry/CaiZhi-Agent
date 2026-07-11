"""
SSE Stream Event Protocol — unified streaming event schema.

Two-tier design:
  Tier 1 (NEW) — StreamEvent: fine-grained streaming events within a single run.
      Covers retrieval progress, generation deltas, and workflow transitions.
      Designed for FastAPI text/event-stream SSE.
  Tier 2 (DEPRECATED) — SSEEvent: coarse stage-completion events.
      Kept for backward compatibility; will be removed once all consumers
      migrate to StreamEvent.

Design principles:
  1. Every event has event_id, run_id, session_id, monotonic sequence
  2. Events are grouped by stage (qa / diagnosis / socratic / feynman / recommendation)
  3. Fine-grained events show retrieval progress, generation progress, and stage changes
  4. run.completed always carries the full result in payload.result
  5. Frontend can filter by event type (SSE "event:" field) or by stage (payload.stage)

Usage — service layer:
    from schemas.events import EventEmitter, StreamEvent

    emitter = EventEmitter(run_id="run_abc123", session_id="session_001", stage="qa")

    # Emit events inside an async generator
    yield emitter.run_started()
    yield emitter.retrieval_started(query="淬火是什么意思？")
    yield emitter.retrieval_source_found(
        file_name="materials_science.md",
        page_start=218,
        chapter="Martensitic Transformations",
        language="en",
    )
    yield emitter.retrieval_completed(source_count=5)
    yield emitter.generation_started()
    yield emitter.generation_delta(section="principle", delta="快速冷却使碳原子来不及扩散……")
    yield emitter.generation_section_completed(section="principle")
    yield emitter.run_completed(result=qa_result.model_dump())

Usage — FastAPI endpoint:
    from fastapi.responses import StreamingResponse
    from api.sse import sse_stream

    @app.get("/api/qa/stream")
    async def stream_qa(session_id: str, question: str):
        async def generate():
            async for event in qa_service.answer_stream(session_id, question):
                yield event.to_sse()
        return StreamingResponse(generate(), media_type="text/event-stream")

SSE wire format:
    event: generation.delta
    id: evt_0014
    data: {"event_id":"evt_0014","run_id":"run_abc123",...}

"""

from __future__ import annotations

import warnings
from datetime import datetime, UTC
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from schemas.common import LearningStage

# ═══════════════════════════════════════════════════════════
# Event type constants
# ═══════════════════════════════════════════════════════════

#: All valid StreamEvent event type strings (dot notation).
EventTypeStr = Literal[
    # Run lifecycle
    "run.started",
    "run.completed",
    "run.failed",
    # Retrieval phase
    "retrieval.started",
    "retrieval.source_found",
    "retrieval.completed",
    # Generation phase
    "generation.started",
    "generation.delta",
    "generation.section_completed",
    # Workflow
    "workflow.stage_changed",
]

#: Human-readable labels for each event type (for logging / debug UI).
EVENT_TYPE_LABELS: dict[str, str] = {
    "run.started": "Run started",
    "run.completed": "Run completed",
    "run.failed": "Run failed",
    "retrieval.started": "Retrieval started",
    "retrieval.source_found": "Source found",
    "retrieval.completed": "Retrieval completed",
    "generation.started": "Generation started",
    "generation.delta": "Generation delta",
    "generation.section_completed": "Section completed",
    "workflow.stage_changed": "Stage changed",
}

# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

def generate_run_id() -> str:
    """Generate a unique run ID: run_{8 hex chars}."""
    return f"run_{uuid4().hex[:8]}"


# ═══════════════════════════════════════════════════════════
# StreamEvent — unified streaming event
# ═══════════════════════════════════════════════════════════

class StreamEvent(BaseModel):
    """
    Unified SSE stream event.

    Every event in the system — from retrieval progress to generation deltas
    to workflow transitions — uses this single schema. The ``event`` field
    (dot notation) determines the semantic meaning; the ``payload`` carries
    event-specific data.

    SSE wire format via ``to_sse()``:

        event: {event}
        id: {event_id}
        data: {full JSON of the StreamEvent}

    The frontend can:
      - Filter by SSE ``event:`` field for coarse routing
      - Parse the JSON ``data:`` for full structured access
      - Sort by ``sequence`` to reconstruct ordering
    """

    event_id: str = Field(
        ...,
        description="Unique event ID within the run, e.g. 'evt_0008'",
        examples=["evt_0008", "evt_0014"],
    )
    run_id: str = Field(
        ...,
        description="Run ID shared by all events in one API call",
        examples=["run_abc123"],
    )
    session_id: str = Field(
        ...,
        description="Learning session ID",
        examples=["session_001"],
    )
    sequence: int = Field(
        ...,
        description="Monotonic sequence number starting from 0, unique within a run",
        examples=[8],
    )
    event: str = Field(
        ...,
        description="Event type in dot notation, e.g. 'generation.delta'",
        examples=["generation.delta", "retrieval.source_found"],
    )
    stage: str = Field(
        ...,
        description=(
            "Learning stage: 'qa' / 'diagnosis' / 'socratic' / 'feynman' / "
            "'recommendation' / 'system'"
        ),
        examples=["qa", "diagnosis"],
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific data payload",
        examples=[{"section": "principle", "delta": "快速冷却使碳原子来不及扩散……"}],
    )

    def to_sse(self) -> str:
        """
        Serialize to SSE protocol format (text/event-stream).

        Returns a string with ``event:``, ``id:``, ``data:`` lines
        followed by a blank line (SSE frame terminator).
        """
        data = self.model_dump_json(exclude_none=True)
        return f"event: {self.event}\nid: {self.event_id}\ndata: {data}\n\n"


# ═══════════════════════════════════════════════════════════
# EventEmitter — factory for sequenced events
# ═══════════════════════════════════════════════════════════

class EventEmitter:
    """
    Creates StreamEvent instances with auto-incrementing sequence numbers.

    One emitter per run. Pass it through the service layer; each service
    method calls the appropriate ``emit_*`` method and yields the result.

    Usage::

        emitter = EventEmitter(run_id="run_abc123", session_id="sess_001", stage="qa")

        # Run lifecycle
        yield emitter.run_started()

        # Retrieval phase
        yield emitter.retrieval_started(query="淬火是什么？")
        for source in rag_results:
            yield emitter.retrieval_source_found(
                file_name=source.file_name,
                page_start=source.page_start,
                chapter=source.chapter,
                language=source.language,
                score=source.score,
            )
        yield emitter.retrieval_completed(source_count=len(rag_results))

        # Generation phase
        yield emitter.generation_started()
        yield emitter.generation_delta(section="principle", delta="快速冷却使碳原子……")
        yield emitter.generation_section_completed(section="principle")

        # Done
        yield emitter.run_completed(result=full_result)
    """

    def __init__(
        self,
        run_id: str | None = None,
        session_id: str = "default",
        stage: str | LearningStage = "qa",
    ) -> None:
        self.run_id = run_id or generate_run_id()
        self.session_id = session_id
        self.stage = stage.value if isinstance(stage, LearningStage) else stage
        self._seq = 0

    # ── internal ──────────────────────────────────────────

    def _next(self, event: str, payload: dict[str, Any] | None = None) -> StreamEvent:
        """Create the next event with auto-incremented sequence."""
        seq = self._seq
        self._seq += 1
        return StreamEvent(
            event_id=f"evt_{seq:04d}",
            run_id=self.run_id,
            session_id=self.session_id,
            sequence=seq,
            event=event,
            stage=self.stage,
            payload=payload or {},
        )

    # ── Run lifecycle ─────────────────────────────────────

    def run_started(self, **extra: Any) -> StreamEvent:
        """Emit when a run (API call) begins."""
        return self._next("run.started", extra if extra else None)

    def run_completed(self, result: dict[str, Any]) -> StreamEvent:
        """
        Emit when a run finishes successfully.

        MUST include the full structured result in ``payload.result``
        so the frontend can render without an extra HTTP request.
        """
        return self._next("run.completed", {"result": result})

    def run_failed(self, error: str, detail: dict[str, Any] | None = None) -> StreamEvent:
        """Emit when a run fails with an error."""
        return self._next("run.failed", {
            "error": error,
            "detail": detail or {},
        })

    # ── Retrieval phase ───────────────────────────────────

    def retrieval_started(self, query: str | None = None) -> StreamEvent:
        """Emit when RAG retrieval begins."""
        p: dict[str, Any] = {}
        if query is not None:
            p["query"] = query
        return self._next("retrieval.started", p)

    def retrieval_source_found(
        self,
        *,
        file_name: str,
        page_start: int | None = None,
        chapter: str | None = None,
        language: str = "zh",
        score: float | None = None,
        chunk_id: str | None = None,
        section: str | None = None,
        **extra: Any,
    ) -> StreamEvent:
        """
        Emit for each relevant source chunk found during retrieval.

        Fires once per source so the frontend can show a live "found sources" list.
        """
        p: dict[str, Any] = {
            "file_name": file_name,
            "language": language,
        }
        if page_start is not None:
            p["page_start"] = page_start
        if chapter is not None:
            p["chapter"] = chapter
        if section is not None:
            p["section"] = section
        if score is not None:
            p["score"] = score
        if chunk_id is not None:
            p["chunk_id"] = chunk_id
        p.update(extra)
        return self._next("retrieval.source_found", p)

    def retrieval_completed(self, source_count: int, **extra: Any) -> StreamEvent:
        """Emit when retrieval phase finishes."""
        return self._next("retrieval.completed", {
            "source_count": source_count,
            **extra,
        })

    # ── Generation phase ──────────────────────────────────

    def generation_started(self) -> StreamEvent:
        """Emit when LLM generation begins."""
        return self._next("generation.started", {})

    def generation_delta(self, section: str, delta: str) -> StreamEvent:
        """
        Emit a text delta during generation.

        ``section`` identifies which part of the output is being generated
        (e.g. 'short_answer', 'principle', 'causal_chain', 'key_terms').
        ``delta`` is the incremental text — can be token-level or sentence-level.
        """
        return self._next("generation.delta", {
            "section": section,
            "delta": delta,
        })

    def generation_section_completed(self, section: str) -> StreamEvent:
        """Emit when a generation section (short_answer / principle / …) is complete."""
        return self._next("generation.section_completed", {"section": section})

    # ── Workflow ──────────────────────────────────────────

    def workflow_stage_changed(
        self,
        from_stage: str,
        to_stage: str,
        reason: str = "",
    ) -> StreamEvent:
        """
        Emit when the learning loop transitions to a new stage.

        Frontend uses this to update the progress indicator and navigate pages.
        """
        return self._next("workflow.stage_changed", {
            "from_stage": from_stage,
            "to_stage": to_stage,
            "reason": reason,
        })


# ═══════════════════════════════════════════════════════════
# Deprecated: Old SSE event types
# ═══════════════════════════════════════════════════════════
#
# These coarse stage-completion events are superseded by StreamEvent.
# Kept for backward compatibility until all consumers migrate.
# New code should use StreamEvent + EventEmitter.
# ═══════════════════════════════════════════════════════════

from enum import StrEnum

from schemas.qa import QAResult
from schemas.diagnosis import DiagnosisResult
from schemas.socratic import SocraticStepResult, SocraticCompleteResult
from schemas.feynman import FeynmanResult
from schemas.recommendation import LearningPathResult


class EventType(StrEnum):
    """DEPRECATED: Use StreamEvent.event string instead."""
    ANSWERING_COMPLETED = "answering_completed"
    DIAGNOSIS_COMPLETED = "diagnosis_completed"
    SOCRATIC_STEP_COMPLETED = "socratic_step_completed"
    SOCRATIC_COMPLETED = "socratic_completed"
    FEYNMAN_COMPLETED = "feynman_completed"
    LEARNING_PATH_GENERATED = "learning_path_generated"
    SESSION_RESET = "session_reset"
    ERROR = "error"


class SSEEvent(BaseModel):
    """
    DEPRECATED: Use StreamEvent instead.

    Coarse stage-completion event. Does not support fine-grained
    streaming (retrieval progress, generation deltas).
    """
    event: EventType = Field(..., description="SSE event type")
    session_id: str = Field(..., description="Session ID")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="Event timestamp (UTC ISO 8601)",
    )
    payload: dict[str, Any] = Field(default_factory=dict, description="Event data")

    def to_sse(self) -> str:
        """Serialize to SSE protocol format."""
        import json
        lines = [
            f"event: {self.event.value}",
            f"id: {self.timestamp}",
            f"data: {json.dumps(self.payload, ensure_ascii=False)}",
            "",
        ]
        return "\n".join(lines)


class AnsweringCompleted(SSEEvent):
    """DEPRECATED: Use StreamEvent(event='workflow.stage_changed', …) instead."""
    event: EventType = Field(default=EventType.ANSWERING_COMPLETED)

    @classmethod
    def from_result(cls, session_id: str, result: QAResult) -> "AnsweringCompleted":
        return cls(
            session_id=session_id,
            payload={
                "knowledge_id": result.knowledge_id,
                "chain_id": result.chain_id,
                "recommended_question_id": result.recommended_question_id,
                "short_answer": result.short_answer,
            },
        )


class DiagnosisCompleted(SSEEvent):
    """DEPRECATED: Use StreamEvent(event='workflow.stage_changed', …) instead."""
    event: EventType = Field(default=EventType.DIAGNOSIS_COMPLETED)

    @classmethod
    def from_result(cls, session_id: str, result: DiagnosisResult) -> "DiagnosisCompleted":
        return cls(
            session_id=session_id,
            payload={
                "question_id": result.question_id,
                "is_correct": result.is_correct,
                "misconception_id": result.misconception_id,
                "recommended_socratic_id": result.recommended_socratic_id,
                "missing_concepts": result.missing_concepts,
            },
        )


class SocraticStepCompleted(SSEEvent):
    """DEPRECATED: Use StreamEvent(event='generation.delta', …) instead."""
    event: EventType = Field(default=EventType.SOCRATIC_STEP_COMPLETED)

    @classmethod
    def from_result(cls, session_id: str, result: SocraticStepResult) -> "SocraticStepCompleted":
        return cls(
            session_id=session_id,
            payload={
                "step_id": result.step_id,
                "action": result.action.value,
                "quality": result.student_answer_quality.value,
                "covered_points": result.covered_points,
                "response": result.response,
            },
        )


class SocraticCompleted(SSEEvent):
    """DEPRECATED: Use StreamEvent(event='workflow.stage_changed', …) instead."""
    event: EventType = Field(default=EventType.SOCRATIC_COMPLETED)

    @classmethod
    def from_result(cls, session_id: str, result: SocraticCompleteResult) -> "SocraticCompleted":
        return cls(
            session_id=session_id,
            payload={
                "socratic_id": result.socratic_id,
                "covered_points": result.covered_points,
                "remaining_weak_points": result.remaining_weak_points,
            },
        )


class FeynmanCompleted(SSEEvent):
    """DEPRECATED: Use StreamEvent(event='workflow.stage_changed', …) instead."""
    event: EventType = Field(default=EventType.FEYNMAN_COMPLETED)

    @classmethod
    def from_result(cls, session_id: str, result: FeynmanResult) -> "FeynmanCompleted":
        return cls(
            session_id=session_id,
            payload={
                "feynman_id": result.feynman_id,
                "total_score": result.total_score,
                "dimension_scores": result.dimension_scores.model_dump(),
                "missing_points": result.missing_points,
                "next_question": result.next_question,
            },
        )


class LearningPathGenerated(SSEEvent):
    """DEPRECATED: Use StreamEvent(event='workflow.stage_changed', …) instead."""
    event: EventType = Field(default=EventType.LEARNING_PATH_GENERATED)

    @classmethod
    def from_result(cls, session_id: str, result: LearningPathResult) -> "LearningPathGenerated":
        return cls(
            session_id=session_id,
            payload={
                "current_level": result.current_level.value,
                "weak_points": [w.model_dump() for w in result.weak_points],
                "recommended_steps": [s.model_dump() for s in result.recommended_steps],
                "total_steps": result.total_recommended_steps,
            },
        )


class SessionReset(SSEEvent):
    """DEPRECATED: Use StreamEvent(event='workflow.stage_changed', to_stage='qa') instead."""
    event: EventType = Field(default=EventType.SESSION_RESET)


class ErrorEvent(SSEEvent):
    """DEPRECATED: Use StreamEvent(event='run.failed', …) instead."""
    event: EventType = Field(default=EventType.ERROR)

    @classmethod
    def from_error(cls, session_id: str, error: str, detail: dict[str, Any] | None = None) -> "ErrorEvent":
        return cls(
            session_id=session_id,
            payload={"error": error, "detail": detail or {}},
        )
