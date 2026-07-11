"""
infrastructure/ — 具体实现层

实现 repositories/ 中定义的抽象接口。
每个模块对应一种具体技术：

    chroma_store.py      → RAGRepository (ChromaDB 实现)
    llm_client.py        → LLM 调用封装 (Anthropic / DeepSeek / OpenAI)
    file_knowledge_repo.py → KnowledgeRepository (JSON/CSV 文件实现)
    memory_session.py    → SessionRepository (内存实现，Streamlit)
    sqlite_session.py    → SessionRepository (SQLite 实现，FastAPI 未来)

原则：
- 所有 I/O 操作（文件、网络、数据库）都在这一层
- 不 import Streamlit
- 实现 repositories 接口，便于替换
"""

# ChromaDB 向量检索
from infrastructure.chroma_store import ChromaStore

# LLM 客户端
from infrastructure.llm_client import LLMClient, create_llm_client

# 文件知识库
from infrastructure.file_knowledge_repo import FileKnowledgeRepository

# 内存会话存储（Streamlit 适配器）
from infrastructure.memory_session import MemorySessionRepository

__all__ = [
    "ChromaStore",
    "LLMClient",
    "create_llm_client",
    "FileKnowledgeRepository",
    "MemorySessionRepository",
]
