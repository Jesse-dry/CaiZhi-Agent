"""
会话路由 — CRUD + 状态查询。

资源：LearningSession — 学习闭环的核心上下文容器。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_session_repo
from repositories.session_repo import SessionRepository
from schemas.learning_session import LearningSession, create_default_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["Sessions"])


class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    user_id: str = Field(default="student_test_01", description="学生标识")
    knowledge_id: str | None = Field(default=None, description="初始知识单元 ID")


class CreateSessionResponse(BaseModel):
    """创建会话响应"""
    session_id: str
    user_id: str
    current_stage: str


@router.post("/", response_model=CreateSessionResponse, status_code=201)
async def create_session(
    body: CreateSessionRequest,
    repo: SessionRepository = Depends(get_session_repo),
):
    """创建新的学习会话，返回初始状态。"""
    session = create_default_session(
        session_id=body.user_id,  # V1: session_id == user_id
        user_id=body.user_id,
    )
    if body.knowledge_id:
        session.current_knowledge_id = body.knowledge_id

    repo.save_session(session)
    return CreateSessionResponse(
        session_id=session.session_id,
        user_id=session.user_id or body.user_id,
        current_stage=session.current_stage.value,
    )


@router.get("/{session_id}", response_model=LearningSession)
async def get_session(
    session_id: str,
    repo: SessionRepository = Depends(get_session_repo),
):
    """获取会话完整状态（包含所有阶段结果和上下文指针）。"""
    session = repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return session


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    repo: SessionRepository = Depends(get_session_repo),
):
    """删除会话及其所有关联数据。"""
    repo.delete_session(session_id)
    return None
