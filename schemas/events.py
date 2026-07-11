"""
SSE 事件定义

学习闭环中每个阶段完成后发出一个事件。
workflows 状态机根据事件推进阶段，前端通过 SSE 订阅实时更新。

每个事件都有明确的 event 类型（用于 SSE event: 字段），
以及类型安全的 payload（不再使用泛型 dict）。
"""

from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, Field
from schemas.qa import QAResult
from schemas.diagnosis import DiagnosisResult
from schemas.socratic import SocraticStepResult, SocraticCompleteResult
from schemas.feynman import FeynmanResult
from schemas.recommendation import LearningPathResult


class EventType(StrEnum):
    """SSE 事件类型 — 对应 event: 字段"""
    ANSWERING_COMPLETED = "answering_completed"
    DIAGNOSIS_COMPLETED = "diagnosis_completed"
    SOCRATIC_STEP_COMPLETED = "socratic_step_completed"
    SOCRATIC_COMPLETED = "socratic_completed"
    FEYNMAN_COMPLETED = "feynman_completed"
    LEARNING_PATH_GENERATED = "learning_path_generated"
    SESSION_RESET = "session_reset"
    ERROR = "error"


# ═══════════════════════════════════════════════════════════
# SSE 事件基类
# ═══════════════════════════════════════════════════════════

class SSEEvent(BaseModel):
    """
    SSE 事件基类。

    所有推送到前端的 SSE 事件共享此结构。
    event 字段用于 SSE 协议的 event: 行，
    data 字段序列化为 JSON 放入 data: 行。
    """
    event: EventType = Field(..., description="SSE 事件类型")
    session_id: str = Field(..., description="会话 ID")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z",
        description="事件时间戳（UTC ISO 8601）",
    )
    payload: dict = Field(default_factory=dict, description="事件携带的数据")

    def to_sse(self) -> str:
        """序列化为 SSE 协议格式"""
        import json
        lines = [
            f"event: {self.event.value}",
            f"id: {self.timestamp}",
            f"data: {json.dumps(self.payload, ensure_ascii=False)}",
            "",
        ]
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 具体事件类型
# ═══════════════════════════════════════════════════════════

class AnsweringCompleted(SSEEvent):
    """智能答疑完成 → 可进入错题诊断"""
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
    """错题诊断完成 → 可进入苏格拉底引导"""
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
    """苏格拉底单步完成（中间事件，前端更新进度条）"""
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
    """苏格拉底引导全部完成 → 可进入费曼评价"""
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
    """费曼评价完成 → 可进入学习路径推荐"""
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
    """学习路径生成完成（学习闭环终点）"""
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
    """会话重置事件"""
    event: EventType = Field(default=EventType.SESSION_RESET)


class ErrorEvent(SSEEvent):
    """错误事件"""
    event: EventType = Field(default=EventType.ERROR)

    @classmethod
    def from_error(cls, session_id: str, error: str, detail: dict | None = None) -> "ErrorEvent":
        return cls(
            session_id=session_id,
            payload={"error": error, "detail": detail or {}},
        )
