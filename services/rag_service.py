"""
RAG 服务层：封装双语检索 + 术语扩展。

上层（pages、agents）通过此服务调用 RAG，不直接依赖 rag/ 或 knowledge/ 模块。
"""

from rag.bilingual_retriever import BilingualRetriever


_retriever = None


def get_retriever() -> BilingualRetriever:
    """获取检索器单例"""
    global _retriever
    if _retriever is None:
        _retriever = BilingualRetriever()
    return _retriever


def search_textbooks(query: str, top_k_each: int = 5) -> dict:
    """
    双语教材检索。

    参数:
        query: 用户查询（中文或英文）
        top_k_each: 每个语种返回的最大片段数

    返回:
        {
            "query": "原始查询",
            "zh_query": "术语扩展后的中文查询",
            "en_query": "术语扩展后的英文查询",
            "matched_terms": [{"zh": "淬火", "en": "quenching", ...}],
            "zh_contexts": [{"text": "...", "metadata": {...}, "distance": 0.23}],
            "en_contexts": [...],
            "image_contexts": [...],
            "merged_contexts": [...]
        }
    """
    retriever = get_retriever()
    return retriever.retrieve(query=query, top_k_each=top_k_each)


def retrieve(query: str, top_k: int = 5) -> dict:
    """
    兼容旧 knowledge.rag_retriever.retrieve() 的接口。

    供 qa_service.py 等旧代码平滑迁移。
    """
    return search_textbooks(query=query, top_k_each=top_k)
