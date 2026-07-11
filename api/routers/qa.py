"""
QA 路由 — 智能答疑。

POST /api/v1/sessions/{session_id}/qa-runs
    创建答疑任务 → 201 {run_id, events_url}
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_qa_service, get_run_store
from api.run_store import RunStore
from infrastructure.event_sinks import RunStoreEventSink
from schemas.runs import CreateRunRequest, RunCreated, RunStatusEnum, RunType
from services.qa_service import QAService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["QA"])


@router.post(
    "/sessions/{session_id}/qa-runs",
    response_model=RunCreated,
    status_code=201,
    summary="创建答疑任务",
    description="""
创建智能答疑任务，返回 run_id 和 SSE 订阅地址。

前端流程:
1. POST 创建任务 → 拿到 run_id + events_url
2. 打开 EventSource(events_url) 接收流式事件
3. 事件结束后可 GET /runs/{run_id} 获取完整结果

事件序列:
    run.started → retrieval.started → retrieval.source_found*N
    → retrieval.completed → generation.started → generation.delta*N
    → generation.section_completed*N → run.completed
""",
)
async def create_qa_run(
    session_id: str,
    body: CreateRunRequest,
    service: QAService = Depends(get_qa_service),
    store: RunStore = Depends(get_run_store),
):
    if not body.question:
        raise HTTPException(status_code=422, detail="question is required for QA run")

    # 1. 在 run_store 创建记录
    record = await store.create(
        session_id=session_id,
        run_type=RunType.QA,
    )

    # 2. 事件出口 → RunStore 缓冲区（SSE 端点从缓冲区读取）
    sink = RunStoreEventSink(store, record.run_id)

    # 3. 后台执行（不阻塞 201 响应）
    from schemas.qa import QARequest
    request = QARequest(
        session_id=session_id,
        question=body.question,
        knowledge_id=body.metadata.get("knowledge_id"),
        language=body.language,
    )

    async def execute():
        try:
            result = await service.answer(request, sink=sink)
            await store.complete(record.run_id, result.model_dump())
        except Exception as exc:
            logger.exception("QA run %s failed", record.run_id)
            await store.fail(record.run_id, str(exc))

    asyncio.create_task(execute())

    # 4. 立即返回
    return RunCreated(
        run_id=record.run_id,
        session_id=session_id,
        run_type=RunType.QA,
        status=RunStatusEnum.PENDING,
        events_url=f"/api/v1/runs/{record.run_id}/events",
        result_url=f"/api/v1/runs/{record.run_id}",
    )
