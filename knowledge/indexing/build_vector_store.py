import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer


BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
VECTOR_DIR = BASE_DIR / "vector_store"

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def load_jsonl(path):
    items = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))

    return items


def build_store(chunks_path: Path, persist_path: Path, collection_name: str):
    chunks = load_jsonl(chunks_path)

    if not chunks:
        print(f"No chunks found: {chunks_path}")
        return

    persist_path.mkdir(parents=True, exist_ok=True)

    model = SentenceTransformer(MODEL_NAME)
    client = chromadb.PersistentClient(path=str(persist_path))

    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.get_or_create_collection(name=collection_name)

    texts = [item["text"] for item in chunks]
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=True
    ).tolist()

    ids = [item["chunk_id"] for item in chunks]

    metadatas = []
    for item in chunks:
        metadatas.append({
            "source_file": item["source_file"],
            "language": item["language"],
            "page": item["page"],
            "chunk_index": item["chunk_index"],
            "topic_hint": item.get("topic_hint", "")
        })

    collection.add(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=embeddings
    )

    print(f"Built {collection_name}: {len(chunks)} chunks")


if __name__ == "__main__":
    build_store(
        PROCESSED_DIR / "chunks_zh.jsonl",
        VECTOR_DIR / "zh_chroma_db",
        "materials_zh"
    )

    build_store(
        PROCESSED_DIR / "chunks_en.jsonl",
        VECTOR_DIR / "en_chroma_db",
        "materials_en"
    )

    build_store(
        PROCESSED_DIR / "chunks_all.jsonl",
        VECTOR_DIR / "all_chroma_db",
        "materials_all"
    )
