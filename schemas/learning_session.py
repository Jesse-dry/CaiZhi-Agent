"""
LearningSession — canonical session model.

This is the SINGLE source of truth for the learning loop state.
It is framework-agnostic: works identically in Streamlit (via st.session_state
cache) and FastAPI (via SQLite/Redis persistence).

Streamlit usage:
    from utils.state import init_session_state, get_learning_session, save_learning_session
    init_session_state()
    session = get_learning_session()
    result = qa_service.answer_question(request)
    session.qa_result = result.model_dump()
    session.current_stage = LearningStage.DIAGNOSIS
    save_learning_session(session)

FastAPI usage (future):
    session = LearningSession(**await db.load(session_id))
    result = qa_service.answer_question(request)
    session.qa_result = result.model_dump()
    session.current_stage = LearningStage.DIAGNOSIS
    await db.save(session.model_dump())
    return result

Key principle:
    st.session_state["learning_session"] is a LOCAL UI CACHE,
    NOT the session manager. The LearningSession model is the authority.
"""

from datetime import datetime, UTC
from pydantic import BaseModel, Field, field_validator
from schemas.common import LearningStage


class LearningSession(BaseModel):
    """
    Cross-stage learning session state.

    Holds context pointers, stage results, and metadata for the full
    5-stage learning loop. Serialisable to JSON for persistence.
    """

    model_config = {"validate_assignment": True}

    # ---- identity ----
    session_id: str = Field(default="default", description="Session unique ID")
    user_id: str | None = Field(default=None, description="Student identifier")

    # ---- stage ----
    current_stage: LearningStage = Field(default=LearningStage.QA, description="Current learning loop stage")

    @field_validator("current_stage", mode="before")
    @classmethod
    def coerce_stage(cls, v: object) -> LearningStage:
        """Accept both string and LearningStage values (transitional compat)."""
        if isinstance(v, LearningStage):
            return v
        if isinstance(v, str):
            return LearningStage(v)
        raise ValueError(f"Invalid stage: {v}")

    # ---- context pointers ----
    current_knowledge_id: str | None = Field(default=None, description="Current knowledge unit ID")
    current_chain_id: str | None = Field(default=None, description="Current causal chain ID")
    current_question_id: str | None = Field(default=None, description="Current self-test question ID")
    current_socratic_id: str | None = Field(default=None, description="Current Socratic chain ID")
    current_feynman_id: str | None = Field(default=None, description="Current Feynman rubric ID")

    # ---- stage results (stored as dicts for flexibility; use model_dump() from Pydantic results) ----
    qa_result: dict | None = Field(default=None, description="QA result (QAResult.model_dump())")
    diagnosis_result: dict | None = Field(default=None, description="Diagnosis result (DiagnosisResult.model_dump())")
    socratic_result: dict | None = Field(default=None, description="Socratic result (SocraticCompleteResult.model_dump())")
    feynman_result: dict | None = Field(default=None, description="Feynman result (FeynmanResult.model_dump())")
    recommendation_result: dict | None = Field(default=None, description="Learning path result (LearningPathResult.model_dump())")

    # ---- versioning ----
    version: int = Field(default=1, description="Schema version for migration compatibility")

    # ---- timestamps ----
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Session creation time (UTC)",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Last update time (UTC)",
    )

    def touch(self) -> None:
        """Update the updated_at timestamp (call before saving)."""
        self.updated_at = datetime.now(UTC)


class SessionSummary(BaseModel):
    """Lightweight session summary for list views (no full history)."""
    session_id: str = Field(..., description="Session ID")
    user_id: str | None = Field(default=None, description="Student ID")
    current_stage: LearningStage = Field(..., description="Current stage")
    version: int = Field(default=1, description="Schema version")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ================================================================
# Factory
# ================================================================

def create_default_session(
    session_id: str = "default",
    user_id: str | None = None,
) -> LearningSession:
    """Create a fresh session with V1 default context pointers."""
    return LearningSession(
        session_id=session_id,
        user_id=user_id or "student_test_01",
        current_stage=LearningStage.QA,
        current_knowledge_id="K001",
        current_chain_id="C001",
        current_question_id="Q001",
        current_socratic_id="S001",
        current_feynman_id="F001",
    )


def reset_session(session: LearningSession) -> LearningSession:
    """Reset to initial state, preserving session_id and user_id."""
    return LearningSession(
        session_id=session.session_id,
        user_id=session.user_id,
    )


# ================================================================
# Streamlit page routes (transitional; moves to frontend router later)
# ================================================================

PAGE_ROUTES: dict[str, str] = {
    "qa": "pages/1_Smart_Answering.py",
    "diagnosis": "pages/2_Error_Diagnosis.py",
    "socratic": "pages/3_Socratic_Guidance.py",
    "feynman": "pages/4_Feynman_Evaluation.py",
    "graph": "pages/5_Knowledge_Graph.py",
    "recommendation": "pages/6_Learning_Path_Recommendation.py",
    "debug": "pages/7_Debug.py",
    "rag_debug": "pages/8_RAG_Debug.py",
}
