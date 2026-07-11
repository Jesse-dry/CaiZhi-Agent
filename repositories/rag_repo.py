"""
RAG 检索数据访问接口

定义了 services 层需要的向量检索能力。
当前实现：ChromaDB（见 infrastructure/chroma_store.py）
未来可替换为：Pinecone、Weaviate、Qdrant 等
"""

from abc import ABC, abstractmethod


class RAGRepository(ABC):
    """
    RAG 检索抽象接口。

    支持双语（zh/en）文本检索 + 图片检索。
    """

    @abstractmethod
    def retrieve(
        self,
        query: str,
        language: str = "zh",
        top_k: int = 5,
    ) -> list[dict]:
        """
        双语语义检索。

        参数:
            query: 查询文本
            language: 目标语言 (zh / en / auto)
            top_k: 返回的 chunk 数量

        返回:
            [
                {
                    "chunk_id": str,
                    "text": str,
                    "language": str,
                    "score": float,
                    "headers": dict,
                    "chapter": str,
                    "section": str,
                    ...
                },
                ...
            ]
        """
        ...

    @abstractmethod
    def retrieve_images(
        self,
        query: str,
        language: str = "zh",
        top_k: int = 3,
    ) -> list[dict]:
        """
        图片检索（按语义匹配图片描述文本）。

        返回:
            [
                {
                    "chunk_id": str,
                    "text": str,        # 图片描述
                    "image_path": str,
                    "image_name": str,
                    "score": float,
                    ...
                },
                ...
            ]
        """
        ...

    @abstractmethod
    def expand_terms(self, term: str, language: str = "zh") -> list[str]:
        """
        术语扩展：把一个术语扩展为双语变体列表，
        用于增强检索召回率。
        """
        ...
