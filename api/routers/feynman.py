"""
费曼评价路由。

POST /api/v1/sessions/{session_id}/feynman-evaluations
    提交费曼解释 → 返回 FeynmanResult
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Feynman"])


class SubmitFeynmanEvaluationRequest(BaseModel):
    """提交费曼评价请求 — session_id 来自 URL"""
    explanation: str = Field(..., description="学生的费曼解释文本", min_length=1, max_length=5000)
    feynman_id: str = Field(default="F001", description="评价标准 ID")


@router.post(
    "/sessions/{session_id}/feynman-evaluations",
    status_code=201,
)
async def submit_feynman_evaluation(
    session_id: str,
    body: SubmitFeynmanEvaluationRequest,
):
    """
    提交费曼解释进行评价。

    返回五维度评分 + 缺失知识点 + 参考示例。

    TODO: 接入 FeynmanService.evaluate()
    """
    raise HTTPException(
        status_code=501,
        detail="Feynman service not yet implemented. Use Streamlit pages/ for now.",
    )
