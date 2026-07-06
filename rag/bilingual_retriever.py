"""
双语检索器：中文 + 英文教材向量库联合检索。

- BGE-m3 embedding
- 自动术语扩展（中→英、英→中）
- 单例模式，首次调用加载模型
"""

import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from knowledge.term_expander import expand_query_with_terms

MODEL_NAME = "BAAI/bge-m3"
BASE_DIR = Path(__file__).resolve().parent.parent
VECTOR_DIR = BASE_DIR / "vector_store"


class BilingualRetriever:
    """
    双语教材检索器。

    用法:
        retriever = BilingualRetriever()
        results = retriever.retrieve("淬火为什么提高硬度？")
    """

    def __init__(
        self,
        zh_db_path: str = None,
        en_db_path: str = None,
        images_db_path: str = None,
        zh_collection_name: str = "materials_zh",
        en_collection_name: str = "materials_en",
        images_collection_name: str = "materials_images",
        model_name: str = MODEL_NAME,
    ):
        self.model = SentenceTransformer(model_name)

        if zh_db_path is None:
            zh_db_path = str(VECTOR_DIR / "zh_chroma_db")
        if en_db_path is None:
            en_db_path = str(VECTOR_DIR / "en_chroma_db")
        if images_db_path is None:
            images_db_path = str(VECTOR_DIR / "images_chroma_db")

        self.zh_client = chromadb.PersistentClient(path=zh_db_path)
        self.en_client = chromadb.PersistentClient(path=en_db_path)

        self.zh_collection = self.zh_client.get_or_create_collection(zh_collection_name)
        self.en_collection = self.en_client.get_or_create_collection(en_collection_name)

        try:
            self.images_client = chromadb.PersistentClient(path=images_db_path)
            self.images_collection = self.images_client.get_or_create_collection(
                images_collection_name
            )
        except Exception:
            self.images_client = None
            self.images_collection = None

    def _query_collection(self, collection, query: str, top_k: int = 5) -> list[dict]:
        query_embedding = self.model.encode(
            [query], normalize_embeddings=True
        ).tolist()[0]

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        output = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # 解析 headers JSON
            headers = {}
            if meta and meta.get("chunk_headers"):
                try:
                    headers = json.loads(meta["chunk_headers"])
                except (json.JSONDecodeError, TypeError):
                    pass

            output.append({
                "text": doc,
                "metadata": {
                    "chunk_id": meta.get("chunk_id", "") if meta else "",
                    "file_name": meta.get("file_name", "") if meta else "",
                    "language": meta.get("language", "") if meta else "",
                    "doc_id": meta.get("doc_id", "") if meta else "",
                    "chunk_index": meta.get("chunk_index", 0) if meta else 0,
                    "chapter": meta.get("chapter", "") if meta else "",
                    "section": meta.get("section", "") if meta else "",
                    "headers": headers,
                    "image_path": meta.get("image_path", "") if meta else "",
                    "image_name": meta.get("image_name", "") if meta else "",
                },
                "distance": dist,
            })

        return output

    def retrieve(self, query: str, top_k_each: int = 5,
                 expand_terms: bool = True) -> dict:
        """
        双语检索主入口。
        """
        if expand_terms:
            expanded = expand_query_with_terms(query)
            zh_query = expanded["zh_query"]
            en_query = expanded["en_query"]
            matched_terms = expanded["matched_terms"]
        else:
            zh_query = query
            en_query = query
            matched_terms = []

        zh_contexts = self._query_collection(self.zh_collection, zh_query, top_k=top_k_each)
        en_contexts = self._query_collection(self.en_collection, en_query, top_k=top_k_each)

        image_contexts = []
        if self.images_collection is not None:
            image_contexts = self._query_collection(self.images_collection, query, top_k=3)

        merged = sorted(
            zh_contexts + en_contexts + image_contexts,
            key=lambda x: x.get("distance", 999),
        )

        return {
            "query": query,
            "zh_query": zh_query,
            "en_query": en_query,
            "matched_terms": matched_terms,
            "zh_contexts": zh_contexts,
            "en_contexts": en_contexts,
            "image_contexts": image_contexts,
            "merged_contexts": merged,
        }
