"""
学习路径推荐路由。

GET /api/v1/sessions/{session_id}/recommendations
    获取个性化学习路径推荐
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Recommendations"])


@router.get("/sessions/{session_id}/recommendations")
async def get_recommendations(session_id: str):
    """
    获取个性化学习路径推荐。

    聚合 diagnosis + socratic + feynman 三个来源的薄弱点，
    按先修关系拓扑排序后返回推荐学习步骤。

    TODO: 接入 RecommendationService.generate_learning_path()
    """
    raise HTTPException(
        status_code=501,
        detail="Recommendation service not yet implemented. Use Streamlit pages/ for now.",
    )
