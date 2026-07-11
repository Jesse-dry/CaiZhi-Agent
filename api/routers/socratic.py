"""
苏格拉底引导路由。

POST /api/v1/sessions/{session_id}/socratic/answers
    提交一步回答 → 返回 SocraticStepResult
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Socratic"])


class SubmitSocraticAnswerRequest(BaseModel):
    """提交苏格拉底引导回答 — session_id 来自 URL"""
    socratic_id: str = Field(..., description="苏格拉底引导链 ID，如 S001")
    step_index: int = Field(..., description="当前步骤序号（1-indexed）", ge=1)
    student_answer: str = Field(..., description="学生回答文本", min_length=1)
    attempt_count: int = Field(default=1, description="当前步骤的尝试次数", ge=1)


@router.post(
    "/sessions/{session_id}/socratic/answers",
    status_code=201,
)
async def submit_socratic_answer(
    session_id: str,
    body: SubmitSocraticAnswerRequest,
):
    """
    提交苏格拉底引导中的一步回答。

    返回当前步骤的评判结果（advance / hint / retry / simplify / complete）。

    TODO: 接入 SocraticService.judge_answer()
    """
    raise HTTPException(
        status_code=501,
        detail="Socratic service not yet implemented. Use Streamlit pages/ for now.",
    )
