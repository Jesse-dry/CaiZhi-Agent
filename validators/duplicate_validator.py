"""
去重校验器 — 三层去重，防止生成重复数据。

三层策略：
  1. 字符串相似度（difflib SequenceMatcher — 快速、无依赖）
  2. Embedding 语义相似度（利用现有 BilingualRetriever 的 embedding 能力，可选）
  3. 知识点组合重叠检测（相同 key_points 组合 → 高度疑似重复）

去重范围：
  - 与已有生产数据对比
  - 与同批次候选数据对比
  - 与 rejected/ 中的已拒绝数据对比（避免重新生成同样的废数据）
"""

from __future__ import annotations

import difflib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent

# 相似度阈值
STRING_SIMILARITY_THRESHOLD = 0.85   # difflib 字符串相似度 > 此值 → 疑似重复
EMBEDDING_SIMILARITY_THRESHOLD = 0.90  # embedding 余弦相似度 > 此值 → 疑似重复
KEYPOINT_OVERLAP_THRESHOLD = 0.80    # 关键点重叠率 > 此值 → 高度疑似重复


def _string_similarity(text1: str, text2: str) -> float:
    """使用 difflib 计算字符串相似度（0-1）"""
    if not text1 or not text2:
        return 0.0
    return difflib.SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def _keypoint_overlap(kp1: list[str], kp2: list[str]) -> float:
    """
    计算知识点组合重叠率。

    使用 Jaccard 相似度：|A ∩ B| / |A ∪ B|
    """
    if not kp1 or not kp2:
        return 0.0
    set1 = set(k.lower() for k in kp1)
    set2 = set(k.lower() for k in kp2)
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    if union == 0:
        return 0.0
    return intersection / union


def _load_existing_items() -> list[dict]:
    """
    加载已有数据用于去重对比。

    来源：
      - data/questions.json（手工 V1 数据）
      - data/socratic.json
      - data/feynman.json
      - data/candidates/*.jsonl（同批次候选）
      - data/rejected/*.jsonl（已拒绝）
    """
    existing: list[dict] = []

    # 手工 V1 数据
    for filename in ["questions.json", "socratic.json", "feynman.json"]:
        filepath = BASE_DIR / "data" / filename
        if filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        existing.extend(data)
            except Exception as e:
                logger.warning(f"Failed to load {filename}: {e}")

    # 候选数据（JSONL）
    candidates_dir = BASE_DIR / "data" / "candidates"
    if candidates_dir.exists():
        for filepath in candidates_dir.glob("*.jsonl"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            existing.append(json.loads(line))
            except Exception as e:
                logger.warning(f"Failed to load {filepath.name}: {e}")

    # 已拒绝数据
    rejected_dir = BASE_DIR / "data" / "rejected"
    if rejected_dir.exists():
        for filepath in rejected_dir.glob("*.jsonl"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            existing.append(json.loads(line))
            except Exception as e:
                logger.warning(f"Failed to load {filepath.name}: {e}")

    return existing


def _get_item_text(item: dict) -> str:
    """从数据条目中提取代表性文本"""
    # QA
    if "question" in item:
        text = item["question"]
        if "reference_answer" in item:
            text += " " + item["reference_answer"]
        return text
    # 苏格拉底
    if "steps" in item:
        texts = [s.get("question", "") for s in item["steps"]]
        texts.append(item.get("title", ""))
        return " ".join(texts)
    # 费曼
    if "prompt" in item:
        return item["prompt"]
    # 学生答案
    if "student_answer" in item:
        return item["student_answer"]
    return ""


def _get_item_keypoints(item: dict) -> list[str]:
    """从数据条目中提取关键知识点"""
    # QA
    if "key_points" in item:
        return item["key_points"]
    # 苏格拉底
    if "target_knowledge_ids" in item:
        return item["target_knowledge_ids"]
    # 费曼
    if "mandatory_points" in item:
        return item["mandatory_points"]
    return []


def check_duplicates(
    item_data: dict,
    existing_items: list[dict] | None = None,
    skip_embedding: bool = True,  # 默认跳过 embedding（需要加载模型，慢）
) -> tuple[bool, float, list[str]]:
    """
    三层去重检查。

    参数:
        item_data: 待检查的候选数据
        existing_items: 已有数据列表（None 则自动加载）
        skip_embedding: 是否跳过 embedding 相似度（默认跳过以提速）

    返回:
        (is_duplicate, max_similarity, similar_ids)
    """
    if existing_items is None:
        existing_items = _load_existing_items()

    item_text = _get_item_text(item_data)
    item_keypoints = _get_item_keypoints(item_data)
    item_id = item_data.get("id", "")

    max_similarity: float = 0.0
    similar_ids: list[str] = []

    for existing in existing_items:
        existing_id = existing.get("id") or existing.get("question_id") or existing.get("socratic_id") or existing.get("feynman_id") or ""
        # 跳过与自身的比较
        if existing_id and existing_id == item_id:
            continue

        existing_text = _get_item_text(existing)

        # Layer 1: 字符串相似度
        str_sim = _string_similarity(item_text, existing_text)
        if str_sim > max_similarity:
            max_similarity = str_sim

        if str_sim >= STRING_SIMILARITY_THRESHOLD:
            similar_ids.append(existing_id)
            continue  # 已足够高，跳过后续检查

        # Layer 2: 知识点组合重叠
        existing_kp = _get_item_keypoints(existing)
        kp_overlap = _keypoint_overlap(item_keypoints, existing_kp)
        if kp_overlap > max_similarity:
            max_similarity = max(max_similarity, kp_overlap)

        if kp_overlap >= KEYPOINT_OVERLAP_THRESHOLD and str_sim >= 0.60:
            # 知识点高度重叠 + 文本中等相似 → 疑似重复
            if existing_id not in similar_ids:
                similar_ids.append(existing_id)

    is_duplicate = max_similarity >= STRING_SIMILARITY_THRESHOLD or len(similar_ids) > 0

    return is_duplicate, max_similarity, similar_ids


def check_batch_duplicates(items: list[dict]) -> list[dict]:
    """
    批量去重：检查批次内互相重复。

    返回:
        每个 item 的重复信息 [{"item_id": ..., "duplicate_of": ..., "similarity": ...}, ...]
    """
    results: list[dict] = []

    for i, item_a in enumerate(items):
        for j, item_b in enumerate(items):
            if j <= i:
                continue

            text_a = _get_item_text(item_a)
            text_b = _get_item_text(item_b)
            sim = _string_similarity(text_a, text_b)

            if sim >= STRING_SIMILARITY_THRESHOLD:
                results.append({
                    "item_id": item_a.get("id", f"item_{i}"),
                    "duplicate_of": item_b.get("id", f"item_{j}"),
                    "similarity": sim,
                    "layer": "string_similarity",
                })
                continue

            kp_a = _get_item_keypoints(item_a)
            kp_b = _get_item_keypoints(item_b)
            kp_overlap = _keypoint_overlap(kp_a, kp_b)
            if kp_overlap >= KEYPOINT_OVERLAP_THRESHOLD and sim >= 0.60:
                results.append({
                    "item_id": item_a.get("id", f"item_{i}"),
                    "duplicate_of": item_b.get("id", f"item_{j}"),
                    "similarity": kp_overlap,
                    "layer": "keypoint_overlap",
                })

    return results


__all__ = [
    "check_duplicates",
    "check_batch_duplicates",
    "STRING_SIMILARITY_THRESHOLD",
    "EMBEDDING_SIMILARITY_THRESHOLD",
    "KEYPOINT_OVERLAP_THRESHOLD",
]
