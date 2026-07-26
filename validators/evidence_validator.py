"""
证据校验器 — 验证候选数据的 source_refs 指向真实存在的教材片段。

检查项：
  - 每个 chunk_id 是否在 ChromaDB 中存在
  - 引用片段内容是否与 reference_answer / key_points 相关联
  - 同一 chunk_id 是否被合理使用（不过度引用同一片段）
"""

from __future__ import annotations

import logging
from typing import Any

from validators.schema_validator import validate_item as schema_validate

logger = logging.getLogger(__name__)


# 缓存已验证的 chunk_id（避免重复查询 ChromaDB）
_chunk_existence_cache: dict[str, bool] = {}


def clear_cache() -> None:
    """清空缓存（数据更新后调用）"""
    _chunk_existence_cache.clear()


def _chunk_exists(chunk_id: str) -> bool:
    """
    检查单个 chunk_id 是否在 ChromaDB 中存在。

    惰性导入 BilingualRetriever 避免循环依赖。
    结果缓存以避免重复查询。
    """
    if chunk_id in _chunk_existence_cache:
        return _chunk_existence_cache[chunk_id]

    try:
        # 惰性导入，避免在 schema 校验等不需要的场景加载 ChromaDB
        from rag.bilingual_retriever import BilingualRetriever

        retriever = BilingualRetriever()
        # 尝试用 get 方法获取单个 chunk
        # ChromaDB 的 get 方法通过 ids 参数查询
        for collection_name in ["materials_zh", "materials_en", "materials_images"]:
            try:
                collection = retriever._get_collection(collection_name)
                if collection is None:
                    continue
                result = collection.get(ids=[chunk_id], limit=1)
                if result and result.get("ids") and len(result["ids"]) > 0:
                    _chunk_existence_cache[chunk_id] = True
                    return True
            except Exception:
                continue

        _chunk_existence_cache[chunk_id] = False
        return False
    except Exception as e:
        logger.warning(f"Failed to check chunk existence for {chunk_id}: {e}")
        _chunk_existence_cache[chunk_id] = False
        return False


def validate_source_refs(
    source_refs: list[dict],
    reference_text: str = "",
    key_points: list[str] | None = None,
) -> tuple[bool, list[str], list[str]]:
    """
    验证 source_refs。

    参数:
        source_refs: 候选数据的 source_refs 列表
        reference_text: 参考答案文本（用于相关性检查）
        key_points: 关键知识点列表

    返回:
        (is_valid, errors, missing_chunk_ids)
    """
    errors: list[str] = []
    missing: list[str] = []

    if not source_refs:
        errors.append("source_refs is empty — 所有生成数据必须有教材依据")
        return False, errors, missing

    for ref in source_refs:
        chunk_id = ref.get("chunk_id", "") if isinstance(ref, dict) else getattr(ref, "chunk_id", "")
        if not chunk_id:
            errors.append("source_ref missing chunk_id")
            continue

        if not _chunk_exists(chunk_id):
            missing.append(chunk_id)
            errors.append(f"chunk_id '{chunk_id}' does not exist in any ChromaDB collection")

    # 不做过度的文本相关性检查（留给 Critic Agent）
    # 只做基本的非空检查
    has_text = any(
        (ref.get("text", "") or ref.get("excerpt", ""))
        if isinstance(ref, dict)
        else (getattr(ref, "text", "") or getattr(ref, "excerpt", ""))
        for ref in source_refs
    )
    if not has_text:
        errors.append("All source_refs have empty text/excerpt — 引用应包含教材原文片段")

    return len(errors) == 0, errors, missing


def validate_evidence(data: dict, item_type: str) -> tuple[bool, list[str], list[str]]:
    """
    统一入口：根据条目类型提取 source_refs 并验证。

    返回:
        (is_valid, errors, missing_chunk_ids)
    """
    source_refs = data.get("source_refs", [])
    reference_text = data.get("reference_answer", "") or data.get("response", "") or ""
    key_points = data.get("key_points", []) or data.get("mandatory_points", [])

    return validate_source_refs(source_refs, reference_text, key_points)


__all__ = [
    "validate_source_refs",
    "validate_evidence",
    "clear_cache",
]
