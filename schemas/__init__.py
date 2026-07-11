"""
schemas/ -- Unified backend data protocol.

All cross-layer types defined as Pydantic v2 BaseModel.
Ready for FastAPI request/response models; frontend can generate
TypeScript types from the OpenAPI schema.

File structure:
    common.py            -- Shared enums and value objects
    learning_session.py  -- LearningSession (canonical session model)
    qa.py                -- QARequest, QAResult, QAStreamChunk
    diagnosis.py         -- DiagnosisRequest, DiagnosisResult
    socratic.py          -- JudgeAnswerRequest, SocraticStepResult, ...
    feynman.py           -- EvaluateRequest, FeynmanResult, DimensionScores
    recommendation.py    -- GeneratePathRequest, LearningPathResult, ...
    events.py            -- SSE events (StreamEvent + EventEmitter)
	    runs.py              -- Run lifecycle (POST create + GET SSE pattern)
	    event_sink.py         -- EventSink protocol (unified event output)

Call chain:
    pages / api -> schemas
    services -> schemas
    workflows -> schemas
    repositories -> schemas

Principles:
    - No bare dicts; every field has an explicit type
    - Every field has a description (auto-generated OpenAPI docs)
    - model_dump() -> dict for backward compat
"""

# ---- common ----
from schemas.common import (
    LearningStage,
    AnswerQuality,
    SocraticAction,
    MasteryLevel,
    Difficulty,
    Language,
    SourceReference,
    KeyTerm,
    ImageReference,
    CausalStep,
    ChatMessage,
)

# ---- learning_session ----
from schemas.learning_session import (
    LearningSession,
    SessionSummary,
    create_default_session,
    reset_session,
    PAGE_ROUTES,
)

# Backward-compat alias (remove once all consumers migrated)
AppSession = LearningSession

# ---- qa ----
from schemas.qa import (
    QARequest,
    QAResult,
    QAStreamChunk,
)

# ---- diagnosis ----
from schemas.diagnosis import (
    DiagnosisRequest,
    MisconceptionDetail,
    DiagnosisResult,
)

# ---- socratic ----
from schemas.socratic import (
    JudgeAnswerRequest,
    SocraticStep,
    SocraticStepResult,
    SocraticChainInfo,
    SocraticCompleteResult,
    SocraticState,
)

# ---- feynman ----
from schemas.feynman import (
    EvaluateRequest,
    DimensionScores,
    ChecklistItem,
    FeynmanRubric,
    FeynmanResult,
)

# ---- recommendation ----
from schemas.recommendation import (
    KnowledgeUnit,
    RecommendedStep,
    GeneratePathRequest,
    WeakPointDetail,
    LearningPathResult,
    LearningPathResultV1,
)

# ---- events (new StreamEvent protocol) ----
from schemas.events import (
    StreamEvent,
    EventEmitter,
    EventTypeStr,
    EVENT_TYPE_LABELS,
    generate_run_id,
    # Deprecated — kept for backward compat
    EventType,
    SSEEvent,
    AnsweringCompleted,
    DiagnosisCompleted,
    SocraticStepCompleted,
    SocraticCompleted,
    FeynmanCompleted,
    LearningPathGenerated,
    SessionReset,
    ErrorEvent,
)

# ---- event_sink ----
from schemas.event_sink import (
    EventSink,
    NullEventSink,
)

# ---- runs ----
from schemas.runs import (
    RunStatusEnum,
    RunType,
    CreateRunRequest,
    RunCreated,
    RunStatusResponse,
    RunListResponse,
    ReplayInfo,
)

__all__ = [
    # common
    "LearningStage",
    "AnswerQuality",
    "SocraticAction",
    "MasteryLevel",
    "Difficulty",
    "Language",
    "SourceReference",
    "KeyTerm",
    "ImageReference",
    "CausalStep",
    "ChatMessage",
    # learning_session
    "LearningSession",
    "AppSession",       # deprecated alias for LearningSession
    "SessionSummary",
    "create_default_session",
    "reset_session",
    "PAGE_ROUTES",
    # qa
    "QARequest",
    "QAResult",
    "QAStreamChunk",
    # diagnosis
    "DiagnosisRequest",
    "MisconceptionDetail",
    "DiagnosisResult",
    # socratic
    "JudgeAnswerRequest",
    "SocraticStep",
    "SocraticStepResult",
    "SocraticChainInfo",
    "SocraticCompleteResult",
    "SocraticState",
    # feynman
    "EvaluateRequest",
    "DimensionScores",
    "ChecklistItem",
    "FeynmanRubric",
    "FeynmanResult",
    # recommendation
    "KnowledgeUnit",
    "RecommendedStep",
    "GeneratePathRequest",
    "WeakPointDetail",
    "LearningPathResult",
    "LearningPathResultV1",
    # events (new StreamEvent protocol)
    "StreamEvent",
    "EventEmitter",
    "EventTypeStr",
    "EVENT_TYPE_LABELS",
    "generate_run_id",
    # events (deprecated)
    "EventType",
    "SSEEvent",
    "AnsweringCompleted",
    "DiagnosisCompleted",
    "SocraticStepCompleted",
    "SocraticCompleted",
    "FeynmanCompleted",
    "LearningPathGenerated",
    "SessionReset",
    "ErrorEvent",
    # event_sink
    "EventSink",
    "NullEventSink",
    # runs
    "RunStatusEnum",
    "RunType",
    "CreateRunRequest",
    "RunCreated",
    "RunStatusResponse",
    "RunListResponse",
    "ReplayInfo",
]
