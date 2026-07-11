"""
错题诊断路由。

POST /api/v1/sessions/{session_id}/diagnoses
    提交答案进行错题诊断 → 返回 DiagnosisResult
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from schemas.diagnosis import DiagnosisResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Diagnosis"])


class SubmitDiagnosisRequest(BaseModel):
    """提交诊断请求 — session_id 来自 URL，不重复放在 body 中"""
    question_id: str = Field(..., description="题目 ID，如 Q001")
    selected_option: str = Field(..., description="学生选择的选项", min_length=1, max_length=1)


@router.post(
    "/sessions/{session_id}/diagnoses",
    response_model=DiagnosisResult,
    status_code=201,
)
async def submit_diagnosis(
    session_id: str,
    body: SubmitDiagnosisRequest,
):
    """
    提交答案进行错题诊断。

    TODO: 接入 DiagnosisService + KnowledgeRepository.diagnose_answer()
          当前占位返回。
    """
    # TODO: service = get_diagnosis_service()
    # TODO: result = await service.diagnose(session_id, body.question_id, body.selected_option)
    raise HTTPException(
        status_code=501,
        detail="Diagnosis service not yet implemented. Use Streamlit pages/ for now.",
    )
