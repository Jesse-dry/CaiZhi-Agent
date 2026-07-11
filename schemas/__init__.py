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
    events.py            -- SSE events

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

# ---- events ----
from schemas.events import (
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
    # events
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
]
