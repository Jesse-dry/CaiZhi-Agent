"""
错题诊断路由。

POST /api/v1/sessions/{session_id}/diagnoses
    提交答案进行错题诊断 → 返回 DiagnosisResult

复用 services/diagnosis_service.py — 与 Streamlit 页面 2_Error_Diagnosis.py 同一套逻辑。
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.diagnosis_service import submit_answer, get_question_for_page, get_all_questions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Diagnosis"])


class SubmitDiagnosisRequest(BaseModel):
    """提交诊断请求 — session_id 来自 URL，不重复放在 body 中"""
    question_id: str = Field(..., description="题目 ID，如 Q001")
    selected_option: str = Field(..., description="学生选择的选项", min_length=1, max_length=1)


@router.get(
    "/questions/{question_id}",
    summary="获取题目详情",
    description="返回题目文本和选项（不含答案），供前端展示。",
)
async def get_question(question_id: str):
    """获取单道题目（展示用，不含答案）"""
    question = get_question_for_page(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail=f"Question {question_id} not found")
    return question


@router.get(
    "/questions",
    summary="获取全部题目列表",
    description="返回题库中所有题目的摘要列表。",
)
async def list_questions():
    """获取全部题目列表"""
    return get_all_questions()


@router.post(
    "/sessions/{session_id}/diagnoses",
    status_code=201,
    summary="提交错题诊断",
    description="""
提交答案进行错题诊断，返回误区定位、缺失知识点、补救路径。

与 Streamlit 页面 2_Error_Diagnosis.py 调用同一函数 submit_answer()。
""",
)
async def submit_diagnosis(
    session_id: str,
    body: SubmitDiagnosisRequest,
):
    """
    提交答案进行错题诊断。

    内部直接调用 services.diagnosis_service.submit_answer()，
    与 Streamlit 页面共享同一套诊断逻辑。返回类型化 Pydantic model。
    """
    sr = submit_answer(body.question_id, body.selected_option)

    if not sr.success or sr.result is None:
        error_msg = sr.errors[0].message if sr.errors else "诊断失败"
        raise HTTPException(
            status_code=404,
            detail=error_msg,
        )

    return sr.result
