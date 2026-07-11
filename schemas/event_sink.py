"""
EventSink 协议 — 统一事件出口。

Agent / Service 层通过此协议发射 StreamEvent，不关心输出端是
Streamlit placeholder、FastAPI SSE 队列、还是测试用的空接收器。

用法::

    from schemas.event_sink import EventSink, NullEventSink

    class QAService:
        async def answer(self, request, sink: EventSink | None = None):
            s = sink or NullEventSink()
            await s.emit(emitter.run_started())
            ...
            await s.emit(emitter.run_completed(result=...))
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from schemas.events import StreamEvent


@runtime_checkable
class EventSink(Protocol):
    """
    事件出口协议。

    任何实现了 ``async emit(event: StreamEvent) -> None`` 的对象
    都可以作为 EventSink 使用。Protocol 类型，无需显式继承。
    """

    async def emit(self, event: StreamEvent) -> None:
        """发射一个流事件到下游。"""
        ...


class NullEventSink:
    """
    空事件接收器 — 静默丢弃所有事件。

    用于：
      - 非流式调用（不需要进度推送）
      - 单元测试（不需要验证事件序列时）
      - Batch 模式（只需最终结果）
    """

    async def emit(self, event: StreamEvent) -> None:
        pass

    def __bool__(self) -> bool:
        return False
