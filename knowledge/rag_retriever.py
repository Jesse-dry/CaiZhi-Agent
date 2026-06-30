from knowledge.retrievers.bilingual_retriever import bilingual_retrieve


def retrieve(query: str, top_k: int = 3):
    return bilingual_retrieve(query=query, top_k=top_k)