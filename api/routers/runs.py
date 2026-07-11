"""
Run 路由 — SSE 事件流 + 结果查询。

GET  /api/v1/runs/{run_id}/events  — SSE 流式事件
GET  /api/v1/runs/{run_id}          — 完整结果
GET  /api/v1/sessions/{session_id}/runs — 会话下所有 run
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from api.dependencies import get_run_store
from api.run_store import RunStore
from schemas.runs import (
    RunStatusEnum,
    RunStatusResponse,
    RunListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Runs"])

# SSE 响应头
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.get(
    "/runs/{run_id}/events",
    summary="SSE 事件流",
    description="""
实时接收 run 的过程事件（text/event-stream）。

支持断线重连：浏览器 EventSource 自动发送 Last-Event-ID 头，
服务端从该序列号的下一个事件开始重放。

EventSource 用法:
    const es = new EventSource(`/api/v1/runs/${runId}/events`);
    es.addEventListener("generation.delta", (e) => {
        const data = JSON.parse(e.data);
        appendText(data.payload.section, data.payload.delta);
    });
    es.addEventListener("run.completed", (e) => {
        renderResult(JSON.parse(e.data).payload.result);
        es.close();
    });
""",
)
async def stream_run_events(
    run_id: str,
    request: Request,
    store: RunStore = Depends(get_run_store),
):
    record = await store.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # 解析 Last-Event-ID
    last_event_id = request.headers.get("Last-Event-ID")
    replay_from = store.replay_from(run_id, last_event_id)

    async def generate():
        # 1. 重放已缓冲但客户端未收到的事件
        if replay_from > 0:
            buffered = await store.get_events_since(run_id, 0)
            for event in buffered[replay_from:]:
                yield event.to_sse()

        # 2. 如果 run 已结束
        if record.status in (RunStatusEnum.COMPLETED, RunStatusEnum.FAILED):
            if replay_from == 0:
                for event in record.events:
                    yield event.to_sse()
            return

        # 3. 等待新事件
        last_index = max(0, len(record.events))
        while True:
            current = await store.get(run_id)
            if current is None:
                break

            if len(current.events) > last_index:
                for event in current.events[last_index:]:
                    yield event.to_sse()
                last_index = len(current.events)

            if current.status in (RunStatusEnum.COMPLETED, RunStatusEnum.FAILED):
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get(
    "/runs/{run_id}",
    response_model=RunStatusResponse,
    summary="获取 run 结果",
    description="获取 run 的完整状态和结果。SSE 流结束后调用此接口确认。",
)
async def get_run(
    run_id: str,
    store: RunStore = Depends(get_run_store),
):
    record = await store.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    return RunStatusResponse(
        run_id=record.run_id,
        session_id=record.session_id,
        run_type=record.run_type,
        status=record.status,
        created_at=record.created_at,
        completed_at=record.completed_at,
        total_events=len(record.events),
        result=record.result,
        error=record.error,
    )


@router.get(
    "/sessions/{session_id}/runs",
    response_model=RunListResponse,
    summary="列出会话 run",
)
async def list_session_runs(
    session_id: str,
    store: RunStore = Depends(get_run_store),
):
    records = await store.list_by_session(session_id)
    runs = [
        RunStatusResponse(
            run_id=r.run_id,
            session_id=r.session_id,
            run_type=r.run_type,
            status=r.status,
            created_at=r.created_at,
            completed_at=r.completed_at,
            total_events=len(r.events),
            result=r.result,
            error=r.error,
        )
        for r in records
    ]
    return RunListResponse(session_id=session_id, runs=runs)


@router.delete(
    "/runs/{run_id}",
    status_code=204,
    summary="删除 run",
)
async def delete_run(
    run_id: str,
    store: RunStore = Depends(get_run_store),
):
    """
    删除 run 及其所有事件数据。

    仅在 run 已完成/失败时可删除，运行中的 run 返回 409。
    """
    record = await store.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    if record.status == RunStatusEnum.RUNNING:
        raise HTTPException(status_code=409, detail="Cannot delete a running run. Wait for completion or cancel first.")

    await store.delete(run_id)
    return None
