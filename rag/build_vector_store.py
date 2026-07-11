"""
构建 ChromaDB 向量库。

Embedding 后端:
  - dashscope (推荐): 阿里云百炼 text-embedding-v4 API，不占本地内存
  - local (默认):    BAAI/bge-m3 本地模型

用法:
    python -m rag.build_vector_store                        # 本地 BGE-M3
    python -m rag.build_vector_store --backend dashscope    # DashScope API
    python -m rag.build_vector_store --backend local        # 本地模型
"""

import argparse
import json
import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()  # 加载 .env 中的 DASHSCOPE_API_KEY

MODEL_NAME = "BAAI/bge-m3"
BASE_DIR = Path(__file__).resolve().parent.parent
# ChromaDB Rust HNSW 不支持中文路径，默认放到 C:\chroma_data\
CHROMA_ROOT = Path(os.environ.get("CHROMA_DATA_DIR", "C:/chroma_data"))
VECTOR_DIR = CHROMA_ROOT
CHUNKS_DIR = BASE_DIR / "data" / "processed" / "chunks"

# 支持的 embedding 后端
BACKENDS = ("local", "dashscope")


def load_jsonl(path: str) -> list[dict]:
    records = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def _create_embedder(backend: str):
    """创建 embedding 编码器。"""
    if backend == "dashscope":
        from rag.dashscope_embedder import DashScopeEmbedder
        print("[Build] Using DashScope text-embedding-v4 API")
        return DashScopeEmbedder()
    else:
        from sentence_transformers import SentenceTransformer
        print(f"[Build] Loading local model: {MODEL_NAME}")
        return SentenceTransformer(MODEL_NAME)


def build_chroma_db(
    chunks_path: str,
    collection_name: str,
    db_path: str = None,
    backend: str = "local",
    batch_size: int = 5,   # DashScope API 长文本限制
):
    chunks = load_jsonl(chunks_path)

    if not chunks:
        print(f"[Build] No chunks found: {chunks_path}")
        return

    if db_path is None:
        db_path = str(VECTOR_DIR / f"{collection_name}_db")

    db_path = Path(db_path)
    db_path.mkdir(parents=True, exist_ok=True)

    # 选择 embedding 后端
    model = _create_embedder(backend)

    # 判断是否需要归一化（API 和本地模型处理方法不同）
    normalize = backend == "local"  # BGE-M3 需要显式归一化; DashScope 在 wrapper 里已处理

    client = chromadb.PersistentClient(path=str(db_path))

    try:
        client.delete_collection(collection_name)
        print(f"[Build] Deleted existing collection: {collection_name}")
    except Exception:
        pass

    collection = client.get_or_create_collection(name=collection_name)

    for i in tqdm(range(0, len(chunks), batch_size),
                  desc=f"Building {collection_name}"):
        batch = chunks[i:i + batch_size]

        ids = [item["chunk_id"] for item in batch]
        texts = [item["text"] for item in batch]

        metadatas = []
        for item in batch:
            headers = item.get("headers", {})
            meta = {
                "file_name": item.get("file_name", ""),
                "doc_id": item.get("doc_id", ""),
                "language": item.get("language", ""),
                "chunk_index": item.get("chunk_index", 0),
                "chunk_id": item.get("chunk_id", ""),
                "chapter": item.get("chapter") or "",
                "section": item.get("section") or "",
                "page_start": item.get("page_start") or 0,
                "page_end": item.get("page_end") or 0,
                "chunk_headers": json.dumps(headers, ensure_ascii=False) if headers else "{}",
                "chunk_type": item.get("chunk_type", "text"),
                "image_path": item.get("image_path", ""),
                "image_name": item.get("image_name", ""),
            }
            metadatas.append(meta)

        # DashScope API 和本地模型使用相同的 encode() 接口
        if isinstance(texts, list) and len(texts) > 0:
            embeddings = model.encode(texts, normalize_embeddings=normalize)
            # API 返回 list[list[float]]，本地返回 numpy array
            if hasattr(embeddings, "tolist"):
                embeddings = embeddings.tolist()
        else:
            embeddings = []

        collection.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    print(f"[Build] Done: {db_path}")
    print(f"  Collection: {collection_name} | Chunks: {len(chunks)}")


def main():
    parser = argparse.ArgumentParser(
        description="构建 ChromaDB 向量库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m rag.build_vector_store                        # 本地 BGE-M3（默认）
  python -m rag.build_vector_store --backend dashscope    # DashScope API（推荐）
  python -m rag.build_vector_store --backend local        # 本地模型
  python -m rag.build_vector_store --collection zh        # 只构建中文
        """,
    )
    parser.add_argument(
        "--backend", choices=BACKENDS, default="local",
        help="Embedding 后端: local (BGE-M3) 或 dashscope (API)",
    )
    parser.add_argument(
        "--collection", choices=("zh", "en", "images", "all"),
        default="all", help="只构建指定集合（默认: all）",
    )
    args = parser.parse_args()

    def build(path_name, coll_name, db_name):
        p = CHUNKS_DIR / path_name
        if p.exists():
            build_chroma_db(
                chunks_path=str(p),
                collection_name=coll_name,
                db_path=str(VECTOR_DIR / db_name),
                backend=args.backend,
            )
        else:
            print(f"[Build] Not found: {p}")

    if args.collection in ("zh", "all"):
        build("zh_chunks.jsonl", "materials_zh", "v2_zh")

    if args.collection in ("en", "all"):
        build("en_chunks.jsonl", "materials_en", "v2_en")

    if args.collection in ("images", "all"):
        build("image_captions.jsonl", "materials_images", "v2_images")


if __name__ == "__main__":
    main()
