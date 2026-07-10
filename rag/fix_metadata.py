"""
修复向量库 metadata：从 JSONL 读取原始数据，用 ChromaDB update 补充缺失的 metadata。
不重新编码 embedding，只更新 metadata 字段。

用法:
    python -m rag.fix_metadata
"""

import json
from pathlib import Path

import chromadb
from tqdm import tqdm

BASE_DIR = Path(__file__).resolve().parent.parent
CHUNKS_DIR = BASE_DIR / "data" / "processed" / "chunks"
VECTOR_DIR = BASE_DIR / "vector_store"

# 三个 collection 的配置
# 重要：ChromaDB Rust HNSW 后端在 Windows 上对含中文的绝对路径有 bug，
# 必须使用相对路径（相对于工作目录）
COLLECTIONS = [
    {
        "name": "materials_zh",
        "db_path": "vector_store/v2_zh",
        "chunks_file": str(CHUNKS_DIR / "zh_chunks.jsonl"),
    },
    {
        "name": "materials_en",
        "db_path": "vector_store/v2_en",
        "chunks_file": str(CHUNKS_DIR / "en_chunks.jsonl"),
    },
    {
        "name": "materials_images",
        "db_path": "vector_store/v2_images",
        "chunks_file": str(CHUNKS_DIR / "image_captions.jsonl"),
    },
]

BATCH_SIZE = 100


def load_jsonl(path: str) -> list[dict]:
    records = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def build_metadata(item: dict) -> dict:
    """从 chunk/item 构建 metadata dict，对齐 build_vector_store.py 的格式"""
    headers = item.get("headers", {})
    return {
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


def fix_collection(cfg: dict) -> int:
    """修复单个 collection 的 metadata，返回更新条数"""
    chunks_path = Path(cfg["chunks_file"])
    if not chunks_path.exists():
        print(f"  [SKIP] Chunks file not found: {chunks_path}")
        return 0

    db_path = Path(cfg["db_path"])
    if not db_path.exists():
        print(f"  [SKIP] Vector store not found: {db_path}")
        return 0

    chunks = load_jsonl(str(chunks_path))
    print(f"  Loaded {len(chunks)} chunks from {chunks_path.name}")

    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_collection(cfg["name"])
    print(f"  Collection '{cfg['name']}': {collection.count()} vectors")

    updated = 0
    for i in tqdm(range(0, len(chunks), BATCH_SIZE),
                  desc=f"  Updating {cfg['name']}"):
        batch = chunks[i:i + BATCH_SIZE]
        ids = [item["chunk_id"] for item in batch]
        metadatas = [build_metadata(item) for item in batch]

        try:
            collection.update(ids=ids, metadatas=metadatas)
            updated += len(batch)
        except Exception as e:
            print(f"  WARNING: batch update failed at offset {i}: {e}")
            # 逐个重试
            for item in batch:
                try:
                    collection.update(
                        ids=[item["chunk_id"]],
                        metadatas=[build_metadata(item)],
                    )
                    updated += 1
                except Exception as e2:
                    print(f"  ERROR: {item['chunk_id']}: {e2}")

    del client
    return updated


def verify_fix(cfg: dict) -> bool:
    """验证 metadata 是否已修复"""
    db_path = Path(cfg["db_path"])
    if not db_path.exists():
        return False

    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_collection(cfg["name"])

    results = collection.get(limit=3, include=["metadatas"])
    metas = results["metadatas"]

    del client

    if not metas or all(m is None for m in metas):
        return False

    # 检查第一个非 None 的 metadata 是否有 chapter
    for m in metas:
        if m is not None:
            return bool(m.get("chunk_headers"))
    return False


def main():
    print("=" * 60)
    print("Fix Vector Store Metadata (no re-embedding)")
    print("=" * 60)

    for cfg in COLLECTIONS:
        print(f"\n[Fix] {cfg['name']}")
        updated = fix_collection(cfg)
        print(f"  Updated: {updated} records")

    print("\n" + "=" * 60)
    print("Verification")
    print("=" * 60)

    all_ok = True
    for cfg in COLLECTIONS:
        ok = verify_fix(cfg)
        status = "OK" if ok else "FAILED"
        if not ok:
            all_ok = False
        print(f"  {cfg['name']}: {status}")

    if all_ok:
        print("\nAll collections fixed. Metadata will now appear in RAG Debug.")
    else:
        print("\nSome collections still have issues. Check the logs above.")


if __name__ == "__main__":
    main()
