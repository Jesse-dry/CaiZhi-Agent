"""
Run 生命周期模型 — POST 创建任务 + GET SSE 订阅模式。

API 模式::

    POST   /api/v1/sessions/{session_id}/qa-runs    创建任务 → 返回 run_id + events_url
    GET    /api/v1/runs/{run_id}/events              SSE 流式接收过程事件
    GET    /api/v1/runs/{run_id}                     获取完整结果（非流式兜底）

支持 SSE 断线重连::

    GET    /api/v1/runs/{run_id}/events
    Header: Last-Event-ID: evt_0005
    → 从 sequence=6 开始重放

设计参考: OpenAI Runs API + SSE Last-Event-ID 标准
"""

from __future__ import annotations

from datetime import datetime, UTC
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════

class RunStatusEnum(StrEnum):
    """Run 生命周期状态"""
    PENDING = "pending"        # 已创建，等待执行
    RUNNING = "running"        # 正在执行（SSE 流推送中）
    COMPLETED = "completed"    # 执行成功
    FAILED = "failed"          # 执行失败


class RunType(StrEnum):
    """Run 类型 — 对应学习闭环中的不同操作"""
    QA = "qa"
    DIAGNOSIS = "diagnosis"
    SOCRATIC = "socratic"
    FEYNMAN = "feynman"
    RECOMMENDATION = "recommendation"


# ═══════════════════════════════════════════════════════════
# 请求模型
# ═══════════════════════════════════════════════════════════

class CreateRunRequest(BaseModel):
    """
    创建 Run 的通用请求体。

    不同 run_type 使用不同字段，但共用同一端点模式。
    具体业务字段由各 service 验证。
    """
    question: str | None = Field(
        default=None,
        description="学生提问（qa run 必填）",
        max_length=5000,
    )
    answer: str | None = Field(
        default=None,
        description="学生答案（diagnosis / socratic / feynman run 使用）",
        max_length=10000,
    )
    question_id: str | None = Field(
        default=None,
        description="当前自测题 ID（diagnosis run 使用）",
    )
    language: str = Field(default="zh", description="期望语言 zh/en/auto")

    # 通用元数据
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="扩展元数据（前端透传，后端不解析）",
    )


# ═══════════════════════════════════════════════════════════
# 响应模型
# ═══════════════════════════════════════════════════════════

class RunCreated(BaseModel):
    """
    POST 创建 Run 的响应。

    前端拿到 run_id 后立即打开 EventSource 订阅事件。
    events_url 是完整的相对路径，前端直接拼接 base URL。
    """
    run_id: str = Field(..., description="Run 唯一标识", examples=["run_a1b2c3d4"])
    session_id: str = Field(..., description="所属会话 ID")
    run_type: RunType = Field(..., description="Run 类型")
    status: RunStatusEnum = Field(default=RunStatusEnum.PENDING)
    events_url: str = Field(
        ...,
        description="SSE 事件流 URL（相对路径）",
        examples=["/api/v1/runs/run_a1b2c3d4/events"],
    )
    result_url: str = Field(
        ...,
        description="完整结果 URL（兜底用）",
        examples=["/api/v1/runs/run_a1b2c3d4"],
    )


class RunStatusResponse(BaseModel):
    """
    GET /api/v1/runs/{run_id} 的响应。

    如果 run 已完成，result 字段包含完整业务结果。
    如果还在运行，前端可据此决定是等待 SSE 还是轮询。
    """
    run_id: str = Field(...)
    session_id: str = Field(...)
    run_type: RunType = Field(...)
    status: RunStatusEnum = Field(...)
    created_at: datetime = Field(...)
    completed_at: datetime | None = Field(default=None)
    total_events: int = Field(default=0, description="已发出的总事件数")
    result: dict[str, Any] | None = Field(
        default=None,
        description="完整业务结果（仅当 status=completed 时有值）",
    )
    error: str | None = Field(
        default=None,
        description="错误信息（仅当 status=failed 时有值）",
    )


class RunListResponse(BaseModel):
    """会话下所有 Run 的列表（轻量，不含完整 result）"""
    session_id: str = Field(...)
    runs: list[RunStatusResponse] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# SSE 重连支持
# ═══════════════════════════════════════════════════════════

class ReplayInfo(BaseModel):
    """
    SSE 重连时的响应头信息。

    当客户端发送 Last-Event-ID 时，服务端从头解析序列号，
    从该序列号的下一个事件开始重放。

    Last-Event-ID 格式: "evt_{sequence:04d}"，如 "evt_0005"
    解析后从 sequence=6 开始重放。
    """
    last_sequence: int = Field(default=-1, description="客户端最后收到的 sequence")
    replay_from: int = Field(default=0, description="从哪个 sequence 开始重放")
    skipped_count: int = Field(default=0, description="跳过了多少个已发送事件")
    total_buffered: int = Field(default=0, description="缓冲区中还有多少事件")

    @classmethod
    def from_last_event_id(cls, last_event_id: str | None, total_events: int) -> "ReplayInfo":
        """
        解析 Last-Event-ID 头，计算重放起点。

        Args:
            last_event_id: 客户端发来的 Last-Event-ID 头（可能为 None）
            total_events: 已发送的总事件数

        Returns:
            ReplayInfo，last_sequence=-1 表示从头开始
        """
        if not last_event_id:
            return cls(last_sequence=-1, replay_from=0, skipped_count=0, total_buffered=total_events)

        # 解析 "evt_0005" → 5
        try:
            prefix, seq_str = last_event_id.rsplit("_", 1)
            if prefix == "evt":
                last_seq = int(seq_str)
                replay_from = last_seq + 1
                skipped = max(0, last_seq + 1)  # 0-indexed: evt_0..evt_5 → 6 events sent
                return cls(
                    last_sequence=last_seq,
                    replay_from=replay_from,
                    skipped_count=min(skipped, total_events),
                    total_buffered=total_events,
                )
        except (ValueError, IndexError):
            pass

        return cls(last_sequence=-1, replay_from=0, skipped_count=0, total_buffered=total_events)
