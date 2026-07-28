"""
知识图谱校验器 — 验证候选数据的 graph_path 节点存在且边关系一致。

检查项：
  - graph_path 中的每个节点 ID 是否在 KG nodes 中存在
  - 相邻节点之间是否存在直接边（方向必须匹配）
  - 边关系方向是否正确（不能出现反向边或将无关联节点强行连接）
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
GRAPH_PATH = BASE_DIR / "data" / "knowledge_graph.json"

# 缓存已加载的 KG（避免重复读取文件）
_kg_cache: dict | None = None
_kg_cache_mtime: float | None = None


def _load_kg() -> dict:
    """加载知识图谱，使用文件修改时间做缓存失效"""
    global _kg_cache, _kg_cache_mtime

    try:
        mtime = GRAPH_PATH.stat().st_mtime
        if _kg_cache is not None and _kg_cache_mtime == mtime:
            return _kg_cache

        with open(GRAPH_PATH, "r", encoding="utf-8") as f:
            _kg_cache = json.load(f)
        _kg_cache_mtime = mtime
        return _kg_cache
    except FileNotFoundError:
        logger.warning(f"Knowledge graph file not found: {GRAPH_PATH}")
        return {"nodes": [], "edges": []}


def clear_kg_cache() -> None:
    """清空 KG 缓存"""
    global _kg_cache, _kg_cache_mtime
    _kg_cache = None
    _kg_cache_mtime = None


def _get_node_map(kg: dict) -> dict[str, dict]:
    """构建 node_id → node 映射"""
    return {n["id"]: n for n in kg.get("nodes", [])}


def _get_edge_set(kg: dict) -> set[tuple[str, str]]:
    """构建 (source, target) 边集合"""
    return {(e["source"], e["target"]) for e in kg.get("edges", [])}


def check_node_exists(node_id: str, node_map: dict[str, dict]) -> tuple[bool, str]:
    """检查节点是否存在"""
    if node_id in node_map:
        return True, ""
    return False, f"KG node '{node_id}' does not exist"


def check_edge_exists(
    source_id: str, target_id: str, edge_set: set[tuple[str, str]]
) -> tuple[bool, str]:
    """检查 (source → target) 有向边是否存在"""
    if (source_id, target_id) in edge_set:
        return True, ""
    # 检查反向边是否存在（如果存在反向边，报告方向错误）
    if (target_id, source_id) in edge_set:
        return False, (
            f"Edge direction mismatch: found edge '{target_id} → {source_id}', "
            f"but graph_path expects '{source_id} → {target_id}'"
        )
    return False, f"No edge found between '{source_id}' and '{target_id}'"


def validate_graph_path(graph_path: list[str]) -> tuple[bool, list[str], list[str]]:
    """
    验证 graph_path 与知识图谱的一致性。

    参数:
        graph_path: 候选数据中的 KG 节点 ID 序列

    返回:
        (is_valid, errors, invalid_nodes)
    """
    errors: list[str] = []
    invalid_nodes: list[str] = []

    if not graph_path:
        errors.append("graph_path is empty — 应包含知识图谱节点序列")
        return False, errors, invalid_nodes

    kg = _load_kg()
    node_map = _get_node_map(kg)
    edge_set = _get_edge_set(kg)

    if not node_map:
        errors.append("Knowledge graph is empty — cannot validate")
        return False, errors, invalid_nodes

    # 1. 检查每个节点是否存在
    for node_id in graph_path:
        exists, msg = check_node_exists(node_id, node_map)
        if not exists:
            invalid_nodes.append(node_id)
            errors.append(msg)

    if invalid_nodes:
        return False, errors, invalid_nodes

    # 2. 检查相邻节点之间是否存在直接边
    for i in range(len(graph_path) - 1):
        source_id = graph_path[i]
        target_id = graph_path[i + 1]
        exists, msg = check_edge_exists(source_id, target_id, edge_set)
        if not exists:
            errors.append(msg)

    return len(errors) == 0, errors, invalid_nodes


def validate_graph_in_item(data: dict, item_type: str) -> tuple[bool, list[str], list[str]]:
    """
    统一入口：根据条目类型提取 graph_path 并验证。
    对于不需要 graph_path 的类型（student_answer, feynman_response），跳过检查。
    """
    if item_type in ("student_answer", "feynman_response"):
        return True, [], []

    graph_path = data.get("graph_path", [])
    return validate_graph_path(graph_path)


__all__ = [
    "validate_graph_path",
    "validate_graph_in_item",
    "clear_kg_cache",
]
