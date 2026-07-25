"""
费曼评价路由。

POST /api/v1/sessions/{session_id}/feynman-evaluations
    提交费曼解释 → 返回 FeynmanResult

复用 services/feynman_service.py — 与 Streamlit 页面 4_Feynman_Evaluation.py 同一套逻辑。
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.feynman_service import load_feynman_rubric, evaluate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Feynman"])


class SubmitFeynmanEvaluationRequest(BaseModel):
    """提交费曼评价请求 — session_id 来自 URL"""
    explanation: str = Field(..., description="学生的费曼解释文本", min_length=1, max_length=5000)
    feynman_id: str = Field(default="F001", description="评价标准 ID")


class FeynmanRubricSummary(BaseModel):
    """费曼评价标准摘要（前端展示用）"""
    feynman_id: str
    topic: str
    chain_id: str
    prompt: str
    checklist_count: int
    rubric: dict


@router.get(
    "/feynman-rubrics/{feynman_id}",
    summary="获取费曼评价标准",
    description="返回评价标准摘要（prompt + checklist 数量 + rubric 权重），不含范例。",
)
async def get_feynman_rubric(feynman_id: str):
    """获取费曼评价标准（前端展示用，不含示例答案）"""
    rubric = load_feynman_rubric(feynman_id)
    if rubric is None:
        raise HTTPException(status_code=404, detail=f"Feynman rubric {feynman_id} not found")

    return {
        "feynman_id": rubric.get("feynman_id"),
        "topic": rubric.get("topic"),
        "chain_id": rubric.get("chain_id"),
        "prompt": rubric.get("prompt"),
        "checklist": rubric.get("checklist", []),
        "rubric": rubric.get("rubric"),
        # 不返回 excellent_example（前端不应直接看到参考答案）
    }


@router.get(
    "/feynman-rubrics",
    summary="获取全部费曼评价标准列表",
    description="返回所有评价标准的 ID 和主题。",
)
async def list_feynman_rubrics():
    """获取全部费曼评价标准列表"""
    import json
    from pathlib import Path

    feynman_path = Path(__file__).resolve().parent.parent.parent / "data" / "feynman.json"
    with open(feynman_path, "r", encoding="utf-8") as f:
        rubrics = json.load(f)

    return [
        {
            "feynman_id": r.get("feynman_id"),
            "topic": r.get("topic"),
            "chain_id": r.get("chain_id"),
        }
        for r in rubrics
    ]


@router.post(
    "/sessions/{session_id}/feynman-evaluations",
    status_code=201,
    summary="提交费曼评价",
    description="""
提交费曼解释进行五维度评价。

与 Streamlit 页面 4_Feynman_Evaluation.py 调用同一函数 evaluate()。
""",
)
async def submit_feynman_evaluation(
    session_id: str,
    body: SubmitFeynmanEvaluationRequest,
):
    """
    提交费曼解释进行评价。

    内部直接调用 services.feynman_service.evaluate()，
    与 Streamlit 页面共享同一套评价逻辑（checklist 关键词匹配 → 五维度打分）。
    """
    rubric = load_feynman_rubric(body.feynman_id)
    if rubric is None:
        raise HTTPException(status_code=404, detail=f"Feynman rubric {body.feynman_id} not found")

    # 调用同一评价函数（与 Streamlit 复用）
    result = evaluate(body.explanation, body.feynman_id)

    return result
