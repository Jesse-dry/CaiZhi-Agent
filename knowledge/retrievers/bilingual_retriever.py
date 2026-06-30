from knowledge.terminology import search_terms
from knowledge.retrievers.zh_retriever import search_zh_textbooks
from knowledge.retrievers.en_retriever import search_en_textbooks


def expand_query_with_terms(query: str):
    """
    第一版简单做：从 terms.csv 里找相关术语，拼接中英文。
    后面可以换成更复杂的术语匹配。
    """
    matched = search_terms(query)

    zh_terms = []
    en_terms = []

    for _, row in matched.iterrows():
        zh_terms.append(str(row.get("zh", "")))
        en_terms.append(str(row.get("en", "")))

    zh_query = " ".join([query] + zh_terms)
    en_query = " ".join(en_terms) if en_terms else query

    return {
        "original_query": query,
        "zh_query": zh_query,
        "en_query": en_query,
        "matched_terms": matched.to_dict(orient="records")
    }


def bilingual_retrieve(query: str, top_k: int = 3):
    expanded = expand_query_with_terms(query)

    zh_contexts = search_zh_textbooks(
        expanded["zh_query"],
        top_k=top_k
    )

    en_contexts = search_en_textbooks(
        expanded["en_query"],
        top_k=top_k
    )

    merged_contexts = zh_contexts + en_contexts
    merged_contexts = sorted(
        merged_contexts,
        key=lambda x: x.get("distance", 999)
    )

    return {
        "query": query,
        "zh_query": expanded["zh_query"],
        "en_query": expanded["en_query"],
        "matched_terms": expanded["matched_terms"],
        "zh_contexts": zh_contexts,
        "en_contexts": en_contexts,
        "merged_contexts": merged_contexts
    }