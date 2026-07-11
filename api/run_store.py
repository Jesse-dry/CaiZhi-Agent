"""
Run Store — 内存运行存储 + SSE 事件缓冲。

职责:
  1. 管理 Run 生命周期（pending → running → completed/failed）
  2. 缓冲 SSE 事件，支持 Last-Event-ID 断线重连
  3. 提供 run 查询接口（GET /runs/{run_id}）

设计要点:
  - 每个 run 的事件全部缓冲在内存列表中（V1 阶段 run 事件量小，~50 events/run）
  - 完成后保留 TTL（5 分钟），超期自动清理
  - 异步安全：FastAPI async 单线程 + asyncio.Lock 足够
  - 为 SQLite 持久化预留接口（RunStore 可替换为 SQLiteRunStore）

用法::

    from api.run_store import run_store

    # 创建 run
    record = await run_store.create(
        run_id="run_abc123",
        session_id="session_001",
        run_type=RunType.QA,
    )

    # 执行过程中追加事件
    await run_store.append_event(run_id, event)

    # SSE 断开后重连 — 从 Last-Event-ID 恢复
    from_sequence = run_store.replay_from(run_id, "evt_0005")
    # → 6，从 events[6:] 开始重放

    # 完成后标记
    await run_store.complete(run_id, result={...})
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any

from schemas.events import StreamEvent, generate_run_id
from schemas.runs import RunStatusEnum, RunType, ReplayInfo

logger = logging.getLogger(__name__)

# 完成后保留时间（秒）
_COMPLETED_TTL_SECONDS = 300  # 5 分钟
# 定期清理间隔（秒）
_CLEANUP_INTERVAL = 60


@dataclass
class RunRecord:
    """一条 run 的完整记录"""
    run_id: str
    session_id: str
    run_type: RunType
    status: RunStatusEnum = RunStatusEnum.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    events: list[StreamEvent] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None


class RunStore:
    """
    内存 Run 存储。

    V1: 纯内存 dict，服务重启丢失。
    V2: 替换为 SQLiteRunStore（infrastructure/sqlite_session.py 风格），
        增删改接口不变。
    """

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None

    async def _ensure_cleanup(self) -> None:
        """启动后台清理任务（只启动一次）"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """后台循环：定期清理过期 run"""
        while True:
            try:
                await asyncio.sleep(_CLEANUP_INTERVAL)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("RunStore cleanup error")

    async def _cleanup_expired(self) -> None:
        """清理超过 TTL 的已完成/失败 run"""
        async with self._lock:
            now = datetime.now(UTC)
            expired = []
            for run_id, record in self._runs.items():
                if record.status in (RunStatusEnum.COMPLETED, RunStatusEnum.FAILED):
                    if record.completed_at is not None:
                        age = (now - record.completed_at).total_seconds()
                        if age > _COMPLETED_TTL_SECONDS:
                            expired.append(run_id)
            for run_id in expired:
                del self._runs[run_id]
            if expired:
                logger.info(f"RunStore cleaned {len(expired)} expired runs")

    # ── CRUD ──────────────────────────────────────────────

    async def create(
        self,
        run_id: str | None = None,
        session_id: str = "default",
        run_type: RunType = RunType.QA,
    ) -> RunRecord:
        """创建一条新 run 记录"""
        await self._ensure_cleanup()

        rid = run_id or generate_run_id()
        record = RunRecord(
            run_id=rid,
            session_id=session_id,
            run_type=run_type,
        )
        async with self._lock:
            self._runs[rid] = record

        logger.info(f"Run created: {rid} (type={run_type}, session={session_id})")
        return record

    async def get(self, run_id: str) -> RunRecord | None:
        """查询 run 记录"""
        async with self._lock:
            return self._runs.get(run_id)

    async def set_status(self, run_id: str, status: RunStatusEnum) -> None:
        """更新 run 状态"""
        async with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                raise ValueError(f"Run not found: {run_id}")
            record.status = status
            if status in (RunStatusEnum.COMPLETED, RunStatusEnum.FAILED):
                record.completed_at = datetime.now(UTC)

    async def append_event(self, run_id: str, event: StreamEvent) -> None:
        """
        追加一个事件到 run 的事件缓冲区。

        同时将状态从 PENDING 改为 RUNNING（首次事件时）。
        """
        async with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                raise ValueError(f"Run not found: {run_id}")
            if record.status == RunStatusEnum.PENDING:
                record.status = RunStatusEnum.RUNNING
            record.events.append(event)

    async def complete(self, run_id: str, result: dict[str, Any]) -> None:
        """标记 run 为已完成，保存结果"""
        async with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                raise ValueError(f"Run not found: {run_id}")
            record.status = RunStatusEnum.COMPLETED
            record.completed_at = datetime.now(UTC)
            record.result = result

    async def fail(self, run_id: str, error: str) -> None:
        """标记 run 为失败"""
        async with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                raise ValueError(f"Run not found: {run_id}")
            record.status = RunStatusEnum.FAILED
            record.completed_at = datetime.now(UTC)
            record.error = error

    async def delete(self, run_id: str) -> None:
        """删除 run 及其所有数据"""
        async with self._lock:
            if run_id not in self._runs:
                raise ValueError(f"Run not found: {run_id}")
            del self._runs[run_id]
        logger.info(f"Run deleted: {run_id}")

    # ── SSE 重连支持 ─────────────────────────────────────

    def replay_from(self, run_id: str, last_event_id: str | None) -> int:
        """
        解析 Last-Event-ID 头，返回重放的起始序列号。

        Args:
            run_id: run ID
            last_event_id: HTTP 头 Last-Event-ID 的值（可能为 None）

        Returns:
            从 events 列表的哪个索引开始重放（0-indexed）
        """
        record = self._runs.get(run_id)  # 无需锁：只读
        if record is None:
            return 0

        total = len(record.events)
        info = ReplayInfo.from_last_event_id(last_event_id, total)

        logger.debug(
            f"SSE replay for {run_id}: last_seq={info.last_sequence}, "
            f"replay_from={info.replay_from}, skipped={info.skipped_count}, "
            f"total={info.total_buffered}"
        )
        return info.replay_from

    async def get_events_since(self, run_id: str, from_sequence: int) -> list[StreamEvent]:
        """获取指定序列号之后的所有事件"""
        async with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return []
            if from_sequence >= len(record.events):
                return []
            return record.events[from_sequence:]

    async def list_by_session(self, session_id: str) -> list[RunRecord]:
        """列出某个会话下的所有 run（最新的在前）"""
        async with self._lock:
            matches = [
                r for r in self._runs.values()
                if r.session_id == session_id
            ]
            matches.sort(key=lambda r: r.created_at, reverse=True)
            return matches


# ═══════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════

run_store = RunStore()
