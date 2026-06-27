import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TERMS_PATH = BASE_DIR / "data" / "terms.csv"


def load_terms():
    """
    读取术语表 terms.csv
    返回 pandas DataFrame
    """
    return pd.read_csv(TERMS_PATH, encoding="utf-8")


def search_terms(keyword: str):
    """
    根据关键词搜索术语。
    可以搜中文、英文、定义。
    """
    df = load_terms()

    if not keyword:
        return df

    keyword = keyword.lower()

    mask = (
        df["zh"].astype(str).str.lower().str.contains(keyword, na=False)
        | df["en"].astype(str).str.lower().str.contains(keyword, na=False)
        | df["definition_zh"].astype(str).str.lower().str.contains(keyword, na=False)
    )

    return df[mask]