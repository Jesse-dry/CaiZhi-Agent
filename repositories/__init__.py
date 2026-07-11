"""
repositories/ — 数据存取抽象接口

定义 services 层需要的所有数据访问能力。
只定义接口（ABC），不实现。
services 依赖这些接口，而非具体的数据源。

具体实现在 infrastructure/ 中：
    KnowledgeRepository  → infrastructure/file_knowledge_repo.py
    RAGRepository        → infrastructure/chroma_store.py
    SessionRepository    → infrastructure/memory_session.py (Streamlit)
                           infrastructure/sqlite_session.py (FastAPI 未来)
"""

from repositories.knowledge_repo import KnowledgeRepository
from repositories.rag_repo import RAGRepository
from repositories.session_repo import SessionRepository

__all__ = [
    "KnowledgeRepository",
    "RAGRepository",
    "SessionRepository",
]
