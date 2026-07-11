"""
ChromaDB 向量检索实现

实现 repositories/rag_repo.py 的 RAGRepository 接口。
封装 BilingualRetriever，提供统一的双语检索入口。

Windows 兼容性：
- 使用相对路径避免中文路径 bug
- 惰性单例避免多客户端文件锁冲突
"""

from pathlib import Path
from repositories.rag_repo import RAGRepository


class ChromaStore(RAGRepository):
    """
    ChromaDB 实现的双语 RAG 检索。

    底层委托给 rag.bilingual_retriever.BilingualRetriever，
    该类处理 ChromaDB Windows 兼容性问题（中文路径、compactor 锁）。

    用法:
        store = ChromaStore()
        results = store.retrieve("淬火为什么提高硬度", language="zh")
        images = store.retrieve_images("Fe-C phase diagram", language="en")
        terms = store.expand_terms("淬火")
    """

    def __init__(self):
        self._retriever = None

    def _get_retriever(self):
        """惰性初始化 BilingualRetriever（单例）"""
        if self._retriever is None:
            from rag.bilingual_retriever import BilingualRetriever
            self._retriever = BilingualRetriever()
        return self._retriever

    def retrieve(
        self,
        query: str,
        language: str = "zh",
        top_k: int = 5,
    ) -> list[dict]:
        retriever = self._get_retriever()
        results = retriever.retrieve(query, language=language, top_k=top_k)
        return results

    def retrieve_images(
        self,
        query: str,
        language: str = "zh",
        top_k: int = 3,
    ) -> list[dict]:
        retriever = self._get_retriever()
        results = retriever.retrieve_images(query, language=language, top_k=top_k)
        return results

    def expand_terms(self, term: str, language: str = "zh") -> list[str]:
        retriever = self._get_retriever()
        return retriever.expand_terms(term, language=language)
