"""
术语校验器 — 验证候选数据中使用的材料学术语在 terms.csv 中存在。

规则：
  - 中英文材料学术语必须存在于 terms.csv
  - 不在表中的术语 → 标记为 unknown_terms，进入待审核术语队列
  - 不能直接发布含未知术语的数据
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
TERMS_PATH = BASE_DIR / "data" / "terms.csv"

# 缓存已加载的术语表
_terms_cache: list[dict] | None = None
_terms_zh_set: set[str] | None = None
_terms_en_set: set[str] | None = None


def _load_terms() -> tuple[list[dict], set[str], set[str]]:
    """加载术语表并构建查找集合"""
    global _terms_cache, _terms_zh_set, _terms_en_set

    if _terms_cache is not None:
        return _terms_cache, _terms_zh_set, _terms_en_set

    terms: list[dict] = []
    zh_set: set[str] = set()
    en_set: set[str] = set()

    try:
        with open(TERMS_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                terms.append(row)
                zh = row.get("zh", "").strip()
                en = row.get("en", "").strip()
                if zh:
                    zh_set.add(zh)
                if en:
                    en_set.add(en.lower())

                # 也加入 aliases
                aliases_zh = row.get("aliases_zh", "").strip()
                aliases_en = row.get("aliases_en", "").strip()
                if aliases_zh:
                    for a in aliases_zh.split("|"):
                        zh_set.add(a.strip())
                if aliases_en:
                    for a in aliases_en.split("|"):
                        en_set.add(a.strip().lower())
    except FileNotFoundError:
        logger.warning(f"Terms file not found: {TERMS_PATH}")

    _terms_cache = terms
    _terms_zh_set = zh_set
    _terms_en_set = en_set
    return terms, zh_set, en_set


def clear_terms_cache() -> None:
    """清空术语缓存"""
    global _terms_cache, _terms_zh_set, _terms_en_set
    _terms_cache = None
    _terms_zh_set = None
    _terms_en_set = None


# 常见的非术语词（不应被标记为 unknown）
_COMMON_WORDS = {
    "的", "是", "在", "和", "与", "或", "不", "了", "着", "过",
    "会", "可以", "能够", "因为", "所以", "但是", "然而", "因此",
    "如果", "那么", "这", "那", "这个", "那个", "这些", "那些",
    "一个", "一种", "一些", "这个", "那个", "什么", "怎么", "为什么",
    "更", "最", "很", "非常", "比较", "特别", "主要", "重要",
    "需要", "应该", "必须", "可能", "通常", "一般", "例如", "比如",
    "通过", "对于", "关于", "根据", "按照", "除了", "以及",
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "of", "to", "in", "for", "on", "with", "at", "by", "from",
    "and", "or", "but", "not", "this", "that", "it", "its",
    "can", "will", "would", "could", "should", "may", "might",
    "more", "most", "very", "also", "has", "have", "had",
    "which", "when", "where", "why", "how", "what",
}


def _extract_materials_terms(text: str) -> list[str]:
    """
    从文本中提取可能的材料学术语。

    简单策略：提取 2-8 个汉字组成的词组（中文术语），
    或由字母组成的 3+ 字符词（英文术语），
    排除了常见虚词。
    """
    candidates: list[str] = []

    # 中文术语：连续的 2-8 个汉字
    zh_pattern = re.compile(r"[一-鿿]{2,8}")
    for match in zh_pattern.finditer(text):
        word = match.group()
        if word not in _COMMON_WORDS:
            candidates.append(word)

    # 英文术语：3+ 字母组成的词
    en_pattern = re.compile(r"[a-zA-Z]{3,}")
    for match in en_pattern.finditer(text):
        word = match.group().lower()
        if word not in _COMMON_WORDS:
            candidates.append(word)

    return candidates


def validate_terminology(texts: list[str]) -> tuple[bool, list[str], list[str]]:
    """
    验证文本中的材料学术语是否在 terms.csv 中。

    参数:
        texts: 需要检查的文本列表（问题、答案、选项、关键点等）

    返回:
        (is_valid, errors, unknown_terms)
    """
    errors: list[str] = []
    unknown_terms: list[str] = []

    _, zh_set, en_set = _load_terms()
    if not zh_set and not en_set:
        errors.append("Terms table is empty — cannot validate terminology")
        return False, errors, unknown_terms

    # 合并所有文本
    combined = " ".join(texts)

    # 提取候选术语
    candidates = _extract_materials_terms(combined)

    # 去重
    seen: set[str] = set()
    for term in candidates:
        term_lower = term.lower()
        if term_lower in seen:
            continue
        seen.add(term_lower)

        # 检查是否在术语表或别名中
        is_known = False
        if term in zh_set:
            is_known = True
        elif term_lower in en_set:
            is_known = True

        if not is_known:
            unknown_terms.append(term)

    if unknown_terms:
        errors.append(
            f"Unknown terms found (not in terms.csv): {', '.join(unknown_terms[:10])}"
            + ("..." if len(unknown_terms) > 10 else "")
        )

    return len(errors) == 0, errors, unknown_terms


def validate_terminology_in_item(data: dict, item_type: str) -> tuple[bool, list[str], list[str]]:
    """
    统一入口：从候选数据中提取所有文本并验证术语。
    """
    texts: list[str] = []

    # 通用字段
    for field in ["question", "reference_answer", "response", "prompt",
                   "student_answer", "final_summary", "excellent_example"]:
        val = data.get(field, "")
        if val:
            texts.append(str(val))

    # options
    options = data.get("options", {})
    if isinstance(options, dict):
        for v in options.values():
            texts.append(str(v))

    # key_points / mandatory_points / expected_concepts
    for list_field in ["key_points", "mandatory_points", "expected_concepts",
                        "expected_diagnosis", "expected_feedback"]:
        val = data.get(list_field, [])
        if isinstance(val, list):
            texts.extend(str(v) for v in val)

    return validate_terminology(texts)


__all__ = [
    "validate_terminology",
    "validate_terminology_in_item",
    "clear_terms_cache",
]
