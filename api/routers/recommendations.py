"""
学习路径推荐路由。

GET /api/v1/sessions/{session_id}/recommendations
    获取个性化学习路径推荐

复用 services/recommendation_service.py — 与 Streamlit 页面 6_Learning_Path_Recommendation.py 同一套逻辑。
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.recommendation_service import generate_learning_path, KNOWLEDGE_UNITS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Recommendations"])


class RecommendationRequest(BaseModel):
    """学习路径推荐请求 — 聚合三个阶段的薄弱点"""
    diagnosis_result: dict | None = Field(default=None, description="诊断结果（submit_answer 返回值）")
    socratic_result: dict | None = Field(default=None, description="苏格拉底完成结果（complete_socratic 返回值）")
    feynman_result: dict | None = Field(default=None, description="费曼评价结果（evaluate 返回值）")


@router.get(
    "/sessions/{session_id}/recommendations",
    summary="获取学习路径推荐（GET，无历史数据时使用）",
    description="""
获取个性化学习路径推荐（不传历史数据时返回默认推荐路径）。

传历史数据请使用 POST 同路径。
""",
)
async def get_recommendations_default(session_id: str):
    """
    无历史数据时的默认推荐路径。
    前端在尚未完成诊断/苏格拉底/费曼阶段时可用此端点获取初始推荐。
    """
    result = generate_learning_path(
        diagnosis_result=None,
        socratic_result=None,
        feynman_result=None,
    )
    return result


@router.post(
    "/sessions/{session_id}/recommendations",
    status_code=200,
    summary="获取个性化学习路径推荐（POST，含历史数据）",
    description="""
聚合 diagnosis + socratic + feynman 三个来源的薄弱点，
按先修关系拓扑排序后返回推荐学习步骤。

与 Streamlit 页面 6_Learning_Path_Recommendation.py 调用同一函数 generate_learning_path()。
""",
)
async def get_recommendations(
    session_id: str,
    body: RecommendationRequest,
):
    """
    获取个性化学习路径推荐。

    内部直接调用 services.recommendation_service.generate_learning_path()，
    与 Streamlit 页面共享同一套推荐逻辑（聚合薄弱点 → 映射知识单元 → 拓扑排序）。
    """
    result = generate_learning_path(
        diagnosis_result=body.diagnosis_result,
        socratic_result=body.socratic_result,
        feynman_result=body.feynman_result,
    )

    return result


@router.get(
    "/knowledge-units",
    summary="获取全部知识单元",
    description="返回推荐系统中定义的 4 个知识单元及先修关系。",
)
async def list_knowledge_units():
    """获取全部知识单元定义"""
    return {
        "units": [
            {
                "knowledge_id": uid,
                "title": unit.get("title"),
                "description": unit.get("description"),
                "prerequisites": unit.get("prerequisites", []),
            }
            for uid, unit in KNOWLEDGE_UNITS.items()
        ]
    }
