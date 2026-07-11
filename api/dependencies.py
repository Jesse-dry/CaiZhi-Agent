"""
FastAPI 依赖注入容器。

所有业务服务通过 Depends() 注入到路由中，路由自身不含业务逻辑。

模式::

    from fastapi import Depends
    from api.dependencies import get_qa_service

    @router.post("/qa-runs")
    async def create_qa(
        body: CreateRunRequest,
        service: QAService = Depends(get_qa_service),
    ):
        return await service.answer(body)

覆盖依赖（测试用）::

    from api import dependencies
    dependencies._rag_override = MockRAGRepo()
"""

from repositories.rag_repo import RAGRepository
from repositories.knowledge_repo import KnowledgeRepository
from repositories.session_repo import SessionRepository
from infrastructure.chroma_store import ChromaStore
from infrastructure.file_knowledge_repo import FileKnowledgeRepository
from infrastructure.llm_client import LLMClient, create_llm_client
from infrastructure.memory_session import MemorySessionRepository
from services.qa_service import QAService
from api.run_store import RunStore, run_store as _global_run_store


# ═══════════════════════════════════════════════════════════
# 模块级单例（可被测试覆盖）
# ═══════════════════════════════════════════════════════════

_rag_repo: RAGRepository | None = None
_knowledge_repo: KnowledgeRepository | None = None
_session_repo: SessionRepository | None = None
_llm_client: LLMClient | None = None
_qa_service: QAService | None = None

# 覆盖钩子（测试时设为 mock 对象）
_rag_override: RAGRepository | None = None
_knowledge_override: KnowledgeRepository | None = None
_llm_override: LLMClient | None = None


# ═══════════════════════════════════════════════════════════
# 基础设施工厂（FastAPI Depends 使用）
# ═══════════════════════════════════════════════════════════

def get_rag_repo() -> RAGRepository:
    """RAG 检索仓库"""
    global _rag_repo
    if _rag_override is not None:
        return _rag_override
    if _rag_repo is None:
        _rag_repo = ChromaStore()
    return _rag_repo


def get_knowledge_repo() -> KnowledgeRepository:
    """知识库仓库"""
    global _knowledge_repo
    if _knowledge_override is not None:
        return _knowledge_override
    if _knowledge_repo is None:
        _knowledge_repo = FileKnowledgeRepository()
    return _knowledge_repo


def get_session_repo() -> SessionRepository:
    """会话仓库"""
    global _session_repo
    if _session_repo is None:
        _session_repo = MemorySessionRepository()
    return _session_repo


def get_llm_client() -> LLMClient:
    """LLM 客户端"""
    global _llm_client
    if _llm_override is not None:
        return _llm_override
    if _llm_client is None:
        _llm_client = create_llm_client()
    return _llm_client


def get_run_store() -> RunStore:
    """Run 存储（全局单例）"""
    return _global_run_store


# ═══════════════════════════════════════════════════════════
# 业务服务工厂
# ═══════════════════════════════════════════════════════════

def get_qa_service() -> QAService:
    """智能答疑服务（单例，依赖自动注入）"""
    global _qa_service
    if _qa_service is None:
        _qa_service = QAService(
            rag_repo=get_rag_repo(),
            knowledge_repo=get_knowledge_repo(),
            llm_client=get_llm_client(),
        )
    return _qa_service


# ═══════════════════════════════════════════════════════════
# 测试辅助
# ═══════════════════════════════════════════════════════════

def reset_all_overrides() -> None:
    """清除所有覆盖和缓存，恢复默认实现"""
    global _rag_repo, _knowledge_repo, _session_repo, _llm_client, _qa_service
    global _rag_override, _knowledge_override, _llm_override
    _rag_repo = None
    _knowledge_repo = None
    _session_repo = None
    _llm_client = None
    _qa_service = None
    _rag_override = None
    _knowledge_override = None
    _llm_override = None
