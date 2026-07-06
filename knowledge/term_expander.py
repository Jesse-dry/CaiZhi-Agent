"""
术语扩展：根据查询中的中英文术语，自动补全对应的翻译。

例如查询"淬火硬度" → 自动追加 "quenching hardness"
"""

import pandas as pd
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TERMS_PATH = BASE_DIR / "data" / "terms.csv"


def load_terms(terms_path: str = None) -> pd.DataFrame:
    if terms_path is None:
        terms_path = str(DEFAULT_TERMS_PATH)
    return pd.read_csv(terms_path)


def expand_query_with_terms(query: str, terms_path: str = None) -> dict:
    """
    对查询做中英文术语扩展。

    参数:
        query: 用户原始查询

    返回:
        {
            "original_query": "淬火硬度",
            "zh_query": "淬火硬度 quenching hardness",   # 中文为主 + 英文术语
            "en_query": "quenching hardness 淬火 硬度",   # 英文为主 + 中文术语
            "matched_terms": [{"zh": "淬火", "en": "quenching"}, ...]
        }
    """
    terms = load_terms(terms_path)

    zh_terms = []
    en_terms = []
    matched = []

    for _, row in terms.iterrows():
        zh = str(row.get("zh", "")).strip()
        en = str(row.get("en", "")).strip()

        if not zh or not en:
            continue

        # 查询中包含中文术语 → 追加英文
        if zh and zh in query:
            en_terms.append(en)
            matched.append({"zh": zh, "en": en})

        # 查询中包含英文术语 → 追加中文
        if en and en.lower() in query.lower():
            zh_terms.append(zh)
            if {"zh": zh, "en": en} not in matched:
                matched.append({"zh": zh, "en": en})

    if not matched:
        return {
            "original_query": query,
            "zh_query": query,
            "en_query": query,
            "matched_terms": [],
        }

    # 中文查询：原始 + 匹配到的英文术语
    zh_query = query
    if en_terms:
        zh_query = query + " " + " ".join(en_terms)

    # 英文查询：原始 / 匹配到的中文术语
    en_query = query
    if zh_terms:
        en_query = query + " " + " ".join(zh_terms)

    return {
        "original_query": query,
        "zh_query": zh_query,
        "en_query": en_query,
        "matched_terms": matched,
    }
