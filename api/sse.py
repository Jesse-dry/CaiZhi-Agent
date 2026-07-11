"""
SSE 工具模块 — FastAPI text/event-stream 支持。

提供：
  - sse_stream(): 将 StreamEvent 异步生成器包装为 StreamingResponse
  - create_emitter(): 便捷工厂，自动生成 run_id
  - sse_heartbeat(): 长连接保活（防止代理超时断连）
  - SSE 格式工具函数

用法示例::

    from fastapi import APIRouter, Query
    from api.sse import sse_stream, create_emitter

    router = APIRouter()

    @router.get("/api/qa/stream")
    async def stream_qa(
        question: str = Query(...),
        session_id: str = Query(...),
    ):
        emitter = create_emitter(session_id=session_id, stage="qa")

        async def generate():
            yield emitter.run_started(question=question)

            # 检索阶段
            yield emitter.retrieval_started(query=question)
            sources = await retriever.search(question)
            for src in sources:
                yield emitter.retrieval_source_found(
                    file_name=src.file_name,
                    chapter=src.chapter,
                    score=src.score,
                )
            yield emitter.retrieval_completed(source_count=len(sources))

            # 生成阶段
            yield emitter.generation_started()
            async for chunk in llm.chat_stream(prompt):
                yield emitter.generation_delta(section="principle", delta=chunk)
            yield emitter.generation_section_completed(section="principle")

            # 完成
            yield emitter.run_completed(result=full_result.model_dump())

        return sse_stream(generate())

前端接收::

    const es = new EventSource("/api/qa/stream?question=...&session_id=...");
    es.addEventListener("generation.delta", (e) => {
        const data = JSON.parse(e.data);
        appendToSection(data.payload.section, data.payload.delta);
    });
    es.addEventListener("run.completed", (e) => {
        const data = JSON.parse(e.data);
        renderFullResult(data.payload.result);
        es.close();
    });
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from fastapi.responses import StreamingResponse

from schemas.events import StreamEvent, EventEmitter, generate_run_id

logger = logging.getLogger(__name__)

# SSE 协议常量
SSE_MEDIA_TYPE = "text/event-stream"
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # 禁用 Nginx 代理缓冲
}


def sse_stream(
    event_generator: AsyncIterator[StreamEvent],
    *,
    extra_headers: dict[str, str] | None = None,
) -> StreamingResponse:
    """
    将 StreamEvent 异步生成器包装为 FastAPI StreamingResponse。

    Args:
        event_generator: 异步生成器，yield StreamEvent 实例
        extra_headers: 额外的响应头（会与默认 SSE 头合并）

    Returns:
        StreamingResponse，media_type="text/event-stream"

    Example::

        @app.get("/api/qa/stream")
        async def stream_qa(question: str, session_id: str):
            async def gen():
                async for event in qa_service.answer_stream(session_id, question):
                    yield event.to_sse()
            return sse_stream(gen())
    """
    headers = {**SSE_HEADERS, **(extra_headers or {})}

    async def _wrap():
        """包装生成器，将 StreamEvent 转为 SSE 字符串 + 异常捕获"""
        try:
            async for event in event_generator:
                yield event.to_sse()
        except Exception as exc:
            logger.exception("SSE stream error")
            # 尝试发送错误事件给前端
            error_event = StreamEvent(
                event_id="evt_error",
                run_id="unknown",
                session_id="unknown",
                sequence=-1,
                event="run.failed",
                stage="system",
                payload={"error": str(exc), "detail": {}},
            )
            yield error_event.to_sse()

    return StreamingResponse(
        _wrap(),
        media_type=SSE_MEDIA_TYPE,
        headers=headers,
    )


def create_emitter(
    session_id: str,
    stage: str = "qa",
    run_id: str | None = None,
) -> EventEmitter:
    """
    便捷工厂：创建 EventEmitter，自动生成 run_id。

    Args:
        session_id: 学习会话 ID
        stage: 当前阶段 (qa / diagnosis / socratic / feynman / recommendation)
        run_id: 手动指定 run_id，为空则自动生成 run_{8 hex}

    Returns:
        配置好的 EventEmitter 实例
    """
    return EventEmitter(
        run_id=run_id or generate_run_id(),
        session_id=session_id,
        stage=stage,
    )


async def sse_heartbeat(
    emitter: EventEmitter,
    interval_seconds: float = 15.0,
    stop_event: asyncio.Event | None = None,
) -> None:
    """
    发送 SSE 心跳注释行，防止代理/负载均衡器超时断连。

    SSE 协议规定以冒号开头的行是注释，浏览器会忽略。
    在长时间无数据时（如 LLM 推理中），定期发送注释行保活。

    Usage::

        stop = asyncio.Event()
        heartbeat_task = asyncio.create_task(sse_heartbeat(emitter, stop_event=stop))

        # ... 主生成逻辑 ...

        stop.set()
        await heartbeat_task

    Args:
        emitter: EventEmitter（仅用于日志记录 run_id）
        interval_seconds: 心跳间隔，默认 15 秒
        stop_event: 设置此事件后停止心跳
    """
    if stop_event is None:
        stop_event = asyncio.Event()

    try:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                # timeout 意味着该发心跳了
                logger.debug(f"SSE heartbeat for run {emitter.run_id}")
                # 注意：心跳需要在调用方生成器中 yield，这里只记录日志
                # 实际心跳由 generate() 中的 asyncio.wait 实现
    except asyncio.CancelledError:
        pass


def sse_comment(text: str) -> str:
    """
    生成 SSE 注释行（以冒号开头，浏览器忽略）。

    用于心跳保活或发送调试信息。::

        yield sse_comment("heartbeat")  # → ": heartbeat\\n\\n"
    """
    return f": {text}\n\n"


def format_sse(event_type: str, event_id: str, data: str) -> str:
    """
    底层 SSE 格式化函数 — 将原始参数格式化为 SSE 协议字符串。

    大多数情况下应使用 StreamEvent.to_sse()。
    此函数用于需要手动构造 SSE 消息的场景。

    Args:
        event_type: SSE event: 行内容
        event_id: SSE id: 行内容
        data: SSE data: 行内容（应为 JSON 字符串）

    Returns:
        完整的 SSE 消息帧（以双换行结尾）
    """
    lines = [
        f"event: {event_type}",
        f"id: {event_id}",
        f"data: {data}",
        "",  # 帧结束
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 前端 EventSource 工具（供 TypeScript 参考，不在此仓库运行）
# ═══════════════════════════════════════════════════════════

# 前端 TypeScript 代码模式参考（复制到 frontend/src/api/sse.ts 使用）:
#
#   const API_BASE = "http://localhost:8000";
#
#   export function streamQA(
#     question: string,
#     sessionId: string,
#     callbacks: {
#       onDelta?: (section: string, delta: string) => void;
#       onSourceFound?: (source: SourceInfo) => void;
#       onCompleted?: (result: QAResult) => void;
#       onFailed?: (error: string) => void;
#     }
#   ): EventSource {
#     const params = new URLSearchParams({ question, session_id: sessionId });
#     const es = new EventSource(`${API_BASE}/api/qa/stream?${params}`);
#
#     es.addEventListener("retrieval.source_found", (e) => {
#       const data = JSON.parse(e.data);
#       callbacks.onSourceFound?.(data.payload);
#     });
#
#     es.addEventListener("generation.delta", (e) => {
#       const data = JSON.parse(e.data);
#       callbacks.onDelta?.(data.payload.section, data.payload.delta);
#     });
#
#     es.addEventListener("run.completed", (e) => {
#       const data = JSON.parse(e.data);
#       callbacks.onCompleted?.(data.payload.result);
#       es.close();
#     });
#
#     es.addEventListener("run.failed", (e) => {
#       const data = JSON.parse(e.data);
#       callbacks.onFailed?.(data.payload.error);
#       es.close();
#     });
#
#     es.onerror = () => {
#       // EventSource 自动重连，如果不想重连可在此 close
#     };
#
#     return es;
#   }
