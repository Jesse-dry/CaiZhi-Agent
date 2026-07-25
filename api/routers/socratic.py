"""
苏格拉底引导路由。

POST /api/v1/sessions/{session_id}/socratic/answers
    提交一步回答 → 返回 SocraticStepResult

复用 services/socratic_service.py — 与 Streamlit 页面 3_Socratic_Guidance.py 同一套逻辑。
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.socratic_service import (
    load_socratic_chain,
    get_step,
    get_total_steps,
    judge_answer,
    complete_socratic,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Socratic"])


class SubmitSocraticAnswerRequest(BaseModel):
    """提交苏格拉底引导回答 — session_id 来自 URL"""
    socratic_id: str = Field(..., description="苏格拉底引导链 ID，如 S001")
    step_index: int = Field(..., description="当前步骤序号（1-indexed）", ge=1)
    student_answer: str = Field(..., description="学生回答文本", min_length=1)
    attempt_count: int = Field(default=1, description="当前步骤的尝试次数", ge=1)


class CompleteSocraticRequest(BaseModel):
    """完成苏格拉底引导请求"""
    socratic_id: str = Field(..., description="苏格拉底引导链 ID")
    covered_points: list[str] = Field(default_factory=list, description="已掌握知识点")
    weak_points: list[str] = Field(default_factory=list, description="薄弱知识点")


@router.get(
    "/socratic-chains/{socratic_id}",
    summary="获取苏格拉底引导链",
    description="返回引导链的完整结构（含所有步骤的题目和提示，不含答案解释）。",
)
async def get_socratic_chain(socratic_id: str):
    """获取苏格拉底引导链（前端展示用）"""
    chain = load_socratic_chain(socratic_id)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Socratic chain {socratic_id} not found")

    # 返回引导链结构（步骤中隐藏 explanation_if_wrong，前端不应提前看到答案）
    steps_safe = []
    for s in chain.get("steps", []):
        steps_safe.append({
            "step": s.get("step"),
            "question": s.get("question"),
            "hint": s.get("hint"),
            # 不返回 expected_keywords 和 explanation_if_wrong
        })

    return {
        "socratic_id": chain.get("socratic_id"),
        "chain_id": chain.get("chain_id"),
        "title": chain.get("title"),
        "total_steps": len(steps_safe),
        "steps": steps_safe,
    }


@router.post(
    "/sessions/{session_id}/socratic/answers",
    status_code=201,
    summary="提交苏格拉底回答",
    description="""
提交苏格拉底引导中的一步回答，返回评判结果。

与 Streamlit 页面 3_Socratic_Guidance.py 调用同一函数 judge_answer()。
""",
)
async def submit_socratic_answer(
    session_id: str,
    body: SubmitSocraticAnswerRequest,
):
    """
    提交苏格拉底引导中的一步回答。

    内部直接调用 services.socratic_service.judge_answer()，
    与 Streamlit 页面共享同一套判定逻辑。
    """
    # 加载引导链
    chain = load_socratic_chain(body.socratic_id)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Socratic chain {body.socratic_id} not found")

    # 获取当前步骤
    step = get_step(chain, body.step_index)
    if step is None:
        raise HTTPException(
            status_code=404,
            detail=f"Step {body.step_index} not found in socratic chain {body.socratic_id}",
        )

    # 调用同一判定函数（与 Streamlit 复用）
    result = judge_answer(step, body.student_answer, body.attempt_count)

    # 补充链级信息
    total_steps = get_total_steps(chain)
    result["socratic_id"] = body.socratic_id
    result["total_steps"] = total_steps
    result["is_last_step"] = (body.step_index >= total_steps and result.get("action") == "advance")
    result["next_step_index"] = (
        body.step_index + 1
        if result.get("action") == "advance" and body.step_index < total_steps
        else body.step_index
    )

    return result


@router.post(
    "/sessions/{session_id}/socratic/complete",
    status_code=201,
    summary="完成苏格拉底引导",
    description="结束苏格拉底引导会话，返回总结。",
)
async def finish_socratic(
    session_id: str,
    body: CompleteSocraticRequest,
):
    """完成苏格拉底引导"""
    chain = load_socratic_chain(body.socratic_id)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Socratic chain {body.socratic_id} not found")

    result = complete_socratic(body.socratic_id, body.covered_points, body.weak_points)
    return result
