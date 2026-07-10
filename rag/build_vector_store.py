"""
构建 ChromaDB 向量库。

- Embedding 模型：BAAI/bge-m3
- 将文本 chunks 和图片 caption chunks 统一入库

用法:
    python -m rag.build_vector_store
"""

import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

MODEL_NAME = "BAAI/bge-m3"
BASE_DIR = Path(__file__).resolve().parent.parent
VECTOR_DIR = BASE_DIR / "vector_store"
CHUNKS_DIR = BASE_DIR / "data" / "processed" / "chunks"


def load_jsonl(path: str) -> list[dict]:
    records = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def build_chroma_db(
    chunks_path: str,
    collection_name: str,
    db_path: str = None,
    model_name: str = MODEL_NAME,
    batch_size: int = 32,
):
    chunks = load_jsonl(chunks_path)

    if not chunks:
        print(f"[Build] No chunks found: {chunks_path}")
        return

    if db_path is None:
        db_path = str(VECTOR_DIR / f"{collection_name}_db")

    db_path = Path(db_path)
    db_path.mkdir(parents=True, exist_ok=True)

    print(f"[Build] Loading model: {model_name}")
    model = SentenceTransformer(model_name)

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
            }
            metadatas.append(meta)

        embeddings = model.encode(texts, normalize_embeddings=True).tolist()

        collection.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    print(f"[Build] Done: {db_path}")
    print(f"  Collection: {collection_name} | Chunks: {len(chunks)}")


def main():
    # 中文文本 chunks
    zh_path = CHUNKS_DIR / "zh_chunks.jsonl"
    if zh_path.exists():
        build_chroma_db(
            chunks_path=str(zh_path),
            collection_name="materials_zh",
            db_path=str(VECTOR_DIR / "v2_zh"),
        )
    else:
        print(f"[Build] Not found: {zh_path}")

    # 英文文本 chunks
    en_path = CHUNKS_DIR / "en_chunks.jsonl"
    if en_path.exists():
        build_chroma_db(
            chunks_path=str(en_path),
            collection_name="materials_en",
            db_path=str(VECTOR_DIR / "v2_en"),
        )
    else:
        print(f"[Build] Not found: {en_path}")

    # 图片 caption chunks（如果有）
    img_path = CHUNKS_DIR / "image_captions.jsonl"
    if img_path.exists():
        build_chroma_db(
            chunks_path=str(img_path),
            collection_name="materials_images",
            db_path=str(VECTOR_DIR / "v2_images"),
        )


if __name__ == "__main__":
    main()
