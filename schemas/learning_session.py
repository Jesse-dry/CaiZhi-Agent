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

from __future__ import annotations

from datetime import datetime, UTC
from pydantic import BaseModel, Field, field_validator
from schemas.common import LearningStage

# 类型化结果模型 — 替代原来的 dict | None
from schemas.qa import QAResult
from schemas.diagnosis import DiagnosisResult
from schemas.socratic import SocraticCompleteResult
from schemas.feynman import FeynmanResult
from schemas.recommendation import LearningPathResult


class LearningSession(BaseModel):
    """
    Cross-stage learning session state.

    Holds context pointers, stage results, and metadata for the full
    5-stage learning loop. Serialisable to JSON for persistence.
    """

    model_config = {"validate_assignment": True}

    # ---- identity ----
    session_id: str = Field(default="default", description="Session unique ID")
    student_id: str | None = Field(default=None, description="学生标识符（提案名）")
    user_id: str | None = Field(default=None, description="[deprecated] 使用 student_id 替代")

    # ---- knowledge context ----
    knowledge_id: str = Field(default="K001", description="当前知识单元 ID（提案统一字段）")

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

    # ---- context pointers (deprecated — 逐步迁移到 knowledge_id + 各阶段 result 中提取) ----
    current_knowledge_id: str | None = Field(default=None, description="[deprecated] 使用 knowledge_id")
    current_chain_id: str | None = Field(default=None, description="[deprecated] 从 qa_result.chain_id 提取")
    current_question_id: str | None = Field(default=None, description="[deprecated] 从 qa_result.recommended_question_id 提取")
    current_socratic_id: str | None = Field(default=None, description="[deprecated] 从 diagnosis_result.recommended_socratic_id 提取")
    current_feynman_id: str | None = Field(default=None, description="[deprecated] 从 socratic_result 推断")

    # ---- stage results (typed Pydantic models — Pydantic v2 auto-coerces dict → model) ----
    qa_result: QAResult | None = Field(default=None, description="QA 阶段结果")
    diagnosis_result: DiagnosisResult | None = Field(default=None, description="错题诊断结果")
    socratic_result: SocraticCompleteResult | None = Field(default=None, description="苏格拉底引导完成结果")
    feynman_result: FeynmanResult | None = Field(default=None, description="费曼评价结果")
    recommendation_result: LearningPathResult | None = Field(default=None, description="学习路径推荐结果")

    # ---- 学习追踪（提案新增） ----
    mastered_concepts: list[str] = Field(default_factory=list, description="已掌握的知识点")
    weak_concepts: list[str] = Field(default_factory=list, description="薄弱知识点")
    misconception_ids: list[str] = Field(default_factory=list, description="触发的误区 ID 列表")

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

    # ── 向后兼容 property ─────────────────────────────────

    @property
    def _user_id(self) -> str | None:
        """向后兼容：优先取 student_id，fallback 到 user_id"""
        return self.student_id or self.user_id

    def touch(self) -> None:
        """Update the updated_at timestamp (call before saving)."""
        self.updated_at = datetime.now(UTC)


class SessionSummary(BaseModel):
    """Lightweight session summary for list views (no full history)."""
    session_id: str = Field(..., description="Session ID")
    student_id: str | None = Field(default=None, description="Student ID")
    user_id: str | None = Field(default=None, description="[deprecated] 使用 student_id")
    current_stage: LearningStage = Field(..., description="Current stage")
    version: int = Field(default=1, description="Schema version")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ================================================================
# Factory
# ================================================================

def create_default_session(
    session_id: str = "default",
    student_id: str | None = None,
) -> LearningSession:
    """Create a fresh session with V1 default context pointers."""
    return LearningSession(
        session_id=session_id,
        student_id=student_id or "student_test_01",
        user_id=student_id or "student_test_01",  # backward compat
        knowledge_id="K001",
        current_stage=LearningStage.QA,
        current_knowledge_id="K001",
        current_chain_id="C001",
        current_question_id="Q001",
        current_socratic_id="S001",
        current_feynman_id="F001",
    )


def reset_session(session: LearningSession) -> LearningSession:
    """Reset to initial state, preserving session_id and student_id."""
    return LearningSession(
        session_id=session.session_id,
        student_id=session.student_id,
        user_id=session.student_id,  # backward compat
        knowledge_id="K001",
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
