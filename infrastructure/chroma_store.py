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
        images = store.retrieve_images("Fe-C phase diagram")
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
        """
        双语语义检索。

        通过 BilingualRetriever 一次性查询 zh + en 两个集合，
        然后根据 language 参数过滤返回结果。

        Args:
            query: 查询文本
            language: zh(仅中文) / en(仅英文) / auto(全部)
            top_k: 返回数量

        Returns:
            list[dict]: 每个元素包含 text, metadata, distance 字段
        """
        retriever = self._get_retriever()
        # retriever.retrieve() 返回 dict，包含 zh_contexts, en_contexts, image_contexts
        raw = retriever.retrieve(query, top_k_each=top_k)

        if language == "zh":
            return raw.get("zh_contexts", [])[:top_k]
        elif language == "en":
            return raw.get("en_contexts", [])[:top_k]
        else:
            # auto: 合并 zh + en，按距离排序
            merged = raw.get("zh_contexts", []) + raw.get("en_contexts", [])
            merged.sort(key=lambda x: x.get("distance", 999))
            return merged[:top_k]

    def retrieve_images(
        self,
        query: str,
        language: str = "zh",
        top_k: int = 3,
    ) -> list[dict]:
        """
        图片检索（按语义匹配图片描述文本）。

        BilingualRetriever 在 retrieve() 中已经查询了 images 集合。
        这里复用其结果，避免重复查询。
        """
        retriever = self._get_retriever()
        raw = retriever.retrieve(query, top_k_each=1)  # 轻量查询，只要 images
        return raw.get("image_contexts", [])[:top_k]

    def expand_terms(self, term: str, language: str = "zh") -> list[str]:
        """
        术语扩展：把一个术语扩展为双语变体列表。

        Args:
            term: 输入术语
            language: 源语言

        Returns:
            list[str]: 扩展后的术语列表（包含中英文变体）
        """
        from knowledge.term_expander import expand_query_with_terms

        expanded = expand_query_with_terms(term)
        matched = expanded.get("matched_terms", [])

        # 提取术语字符串列表
        terms: list[str] = []
        for t in matched:
            zh = t.get("zh", "")
            en = t.get("en", "")
            if zh:
                terms.append(zh)
            if en and en != zh:
                terms.append(en)

        # 兜底：直接返回原词
        if not terms:
            terms.append(term)

        return terms
