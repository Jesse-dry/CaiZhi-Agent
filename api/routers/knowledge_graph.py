"""
知识图谱路由。

GET /api/v1/sessions/{session_id}/knowledge-graph
    获取当前会话上下文的知识图谱（节点 + 边 + 因果链）
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_knowledge_repo
from repositories.knowledge_repo import KnowledgeRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Knowledge Graph"])


@router.get("/sessions/{session_id}/knowledge-graph")
async def get_knowledge_graph(
    session_id: str,
    repo: KnowledgeRepository = Depends(get_knowledge_repo),
):
    """
    获取知识图谱数据。

    返回 nodes、edges、chains 用于前端可视化。
    可根据 session 上下文过滤（当前知识单元关联的子图）。
    """
    graph = repo.get_knowledge_graph()

    return {
        "session_id": session_id,
        "nodes": graph.get("nodes", []),
        "edges": graph.get("edges", []),
        "chains": graph.get("chains", []),
    }
