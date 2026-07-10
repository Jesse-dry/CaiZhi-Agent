"""
双语检索器：中文 + 英文教材向量库联合检索。

- BGE-m3 embedding
- 自动术语扩展（中→英、英→中）
- 惰性 PersistentClient：同一时间只保持一个客户端连接，避免 Windows 文件锁冲突
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
    惰性 PersistentClient：每次查询时打开单个客户端，用完即释放。

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

        # 只存路径和集合名，不提前打开客户端
        # 注意：ChromaDB Rust 后端对含中文的绝对路径有 HNSW bug，统一用相对路径
        if zh_db_path is None:
            zh_db_path = "vector_store/v2_zh"
        if en_db_path is None:
            en_db_path = "vector_store/v2_en"
        if images_db_path is None:
            images_db_path = "vector_store/v2_images"

        self._db_paths = {
            "zh": zh_db_path,
            "en": en_db_path,
            "images": images_db_path,
        }
        self._collection_names = {
            "zh": zh_collection_name,
            "en": en_collection_name,
            "images": images_collection_name,
        }

    def _get_collection(self, key: str):
        """惰性获取单个 collection——打开 client → 取 collection → 返回。
        不持有 client 引用，让 GC 自动回收，避免 Windows 多客户端文件锁冲突。
        用 get_collection 而非 get_or_create_collection，避免触发 compactor。"""
        db_path = self._db_paths[key]
        name = self._collection_names[key]
        client = chromadb.PersistentClient(path=db_path)
        return client.get_collection(name)

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
        依次查询 zh → en → images，每个客户端用完即释放。
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

        # 逐个查询，同一时间只有一个 PersistentClient 存活
        zh_coll = self._get_collection("zh")
        zh_contexts = self._query_collection(zh_coll, zh_query, top_k=top_k_each)
        del zh_coll  # 释放客户端

        en_coll = self._get_collection("en")
        en_contexts = self._query_collection(en_coll, en_query, top_k=top_k_each)
        del en_coll

        image_contexts = []
        try:
            img_coll = self._get_collection("images")
            image_contexts = self._query_collection(img_coll, query, top_k=3)
            del img_coll
        except Exception:
            pass

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
