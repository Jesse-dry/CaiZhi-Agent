from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer


BASE_DIR = Path(__file__).resolve().parent.parent.parent
VECTOR_PATH = BASE_DIR / "vector_store" / "en_chroma_db"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


_model = None
_collection = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(VECTOR_PATH))
        _collection = client.get_or_create_collection(name="materials_en")
    return _collection


def search_en_textbooks(query: str, top_k: int = 3):
    model = get_model()
    collection = get_collection()

    query_embedding = model.encode(
        [query],
        normalize_embeddings=True
    ).tolist()

    result = collection.query(
        query_embeddings=query_embedding,
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )

    outputs = []

    for doc, meta, distance in zip(
        result["documents"][0],
        result["metadatas"][0],
        result["distances"][0]
    ):
        outputs.append({
            "language": "en",
            "text": doc,
            "metadata": meta,
            "distance": distance
        })

    return outputs