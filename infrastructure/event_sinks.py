"""
EventSink 具体实现 — 对应不同输出端。

  NullEventSink         → schemas/event_sink.py  (无输出)
  StreamlitEventSink    → 本文件                   (Streamlit UI)
  RunStoreEventSink     → 本文件                   (FastAPI SSE 缓冲区)

所有实现都满足 EventSink 协议（Duck typing，无需显式继承）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from schemas.events import StreamEvent

if TYPE_CHECKING:
    from api.run_store import RunStore

logger = logging.getLogger(__name__)


class StreamlitEventSink:
    """
    Streamlit 事件出口 — 在 Streamlit placeholder 中渲染增量内容。

    用法::

        placeholder = st.empty()
        sink = StreamlitEventSink(placeholder)
        await service.answer(request, sink=sink)

    只处理 generation.delta 事件，其他事件静默忽略。
    """

    def __init__(self, placeholder: object) -> None:
        """
        Args:
            placeholder: st.empty() 或 st.container() 返回的 DeltaGenerator
        """
        self.placeholder = placeholder
        self._buffer: dict[str, str] = {}  # section → accumulated text
        self._current_section: str = ""

    async def emit(self, event: StreamEvent) -> None:
        """处理 StreamEvent，增量更新 placeholder。"""
        if event.event == "generation.delta":
            section = event.payload.get("section", "")
            delta = event.payload.get("delta", "")

            # 收集各 section 的文本
            if section not in self._buffer:
                self._buffer[section] = ""
            self._buffer[section] += delta
            self._current_section = section

            # 更新 Streamlit placeholder
            self._render()

        elif event.event == "generation.section_completed":
            section = event.payload.get("section", "")
            logger.debug("Streamlit: section %s completed", section)

        elif event.event == "retrieval.source_found":
            # 可选：在 UI 中展示"找到来源"提示
            file_name = event.payload.get("file_name", "")
            logger.debug("Streamlit: source found → %s", file_name)

    def _render(self) -> None:
        """重新渲染 placeholder 内容。"""
        try:
            sections = []
            for section_name in ["short_answer", "principle", "causal_chain", "key_terms"]:
                text = self._buffer.get(section_name, "")
                if text:
                    if section_name == "short_answer":
                        sections.append(f"**简明回答**\n\n{text}")
                    elif section_name == "principle":
                        sections.append(f"**原理**\n\n{text}")
                    elif section_name == "causal_chain":
                        sections.append(f"**因果链**\n\n{text}")
                    elif section_name == "key_terms":
                        sections.append(f"**关键术语**\n\n{text}")

            if sections:
                self.placeholder.markdown("\n\n---\n\n".join(sections))
        except Exception:
            # placeholder 可能已被销毁，忽略
            pass


class RunStoreEventSink:
    """
    FastAPI SSE 事件出口 — 将事件缓冲到 RunStore。

    用于 POST 创建任务后的后台执行。Run 的事件全部写入 RunStore，
    SSE 端点从 RunStore 读取并推送给前端。

    用法::

        sink = RunStoreEventSink(store, run_id)
        await service.answer(request, sink=sink)
        # 所有事件已缓冲到 store，SSE 端点可读取
    """

    def __init__(self, store: RunStore, run_id: str) -> None:
        """
        Args:
            store: RunStore 实例
            run_id: 当前 run 的 ID
        """
        self.store = store
        self.run_id = run_id

    async def emit(self, event: StreamEvent) -> None:
        """将事件追加到 RunStore 缓冲区。"""
        try:
            await self.store.append_event(self.run_id, event)
        except Exception:
            logger.exception("RunStoreEventSink: failed to append event %s", event.event)


class QueueEventSink:
    """
    队列事件出口 — 将事件放入 asyncio.Queue。

    用于需要精确控制背压的场景（如 SSE 端点直接与 agent 通信）。
    消费者从队列中读取事件并通过 SSE 推送。

    用法::

        queue: asyncio.Queue[StreamEvent] = asyncio.Queue()
        sink = QueueEventSink(queue)

        # 生产者
        await service.answer_stream(request)  # 内部调用 sink.emit()

        # 消费者（SSE 端点）
        while True:
            event = await queue.get()
            yield event.to_sse()
    """

    def __init__(self, queue: asyncio.Queue[StreamEvent]) -> None:
        self.queue = queue

    async def emit(self, event: StreamEvent) -> None:
        await self.queue.put(event)


class CallbackEventSink:
    """
    回调事件出口 — 将事件转发到回调函数。

    支持同步和异步回调。用于轻量场景或自定义事件处理。

    用法::

        # 异步回调
        sink = CallbackEventSink(lambda e: store.append_event(run_id, e))

        # 同步回调（自动适配）
        sink = CallbackEventSink(lambda e: print(f"{e.event}"))
    """

    def __init__(self, callback):
        """
        Args:
            callback: (StreamEvent) -> None | Awaitable[None]
        """
        self._callback = callback
        self._is_async = _is_async_callable(callback)

    async def emit(self, event: StreamEvent) -> None:
        result = self._callback(event)
        if self._is_async:
            await result


def _is_async_callable(obj) -> bool:
    """检测是否为异步可调用对象（函数/方法/lambda）"""
    import inspect
    if inspect.iscoroutinefunction(obj):
        return True
    # 检查是否有 __call__ 且是 coroutine function（如 partial 包装的 async func）
    call_method = getattr(obj, "__call__", None)
    if call_method is not None:
        return inspect.iscoroutinefunction(call_method)
    return False
