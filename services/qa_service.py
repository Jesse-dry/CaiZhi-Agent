"""
统一答疑服务 — QAService。

职责：组合四个数据源 → 构建约束型回答 → 返回 QAResult。
四个数据源各有边界，互不越界：
  1. RAG (教材)       → 事实依据（定义、原理、组织转变、性能变化）
  2. Knowledge Graph  → 因果链路径
  3. Terms (术语表)   → 术语标准翻译（禁止 LLM 自造）
  4. Questions (题库) → 自测题匹配（禁止 LLM 临时出题）

架构原则（用户确认）:
  - 类化 + 构造器注入：所有依赖通过 __init__ 传入，不硬编码 import
  - 与传输层无关：不依赖 Streamlit 或 FastAPI
  - event_sink 模式：可选回调，支持 SSE 流式推送
  - 同一份代码服务 Streamlit 和 FastAPI

用法:
    # 构造（FastAPI 用 Depends，Streamlit 用工厂函数）
    service = QAService(
        rag_repo=ChromaStore(),
        knowledge_repo=FileKnowledgeRepository(),
        llm_client=create_llm_client(),
    )

    # 非流式：直接返回结果
    result = await service.answer(QARequest(session_id="s1", question="淬火？"))

    # 流式：通过 event_sink 推送进度
    async def sink(event: StreamEvent):
        await run_store.append_event(run_id, event)

    result = await service.answer(request, event_sink=sink)

    # 流式生成器（FastAPI SSE 用）
    async for event in service.answer_stream(request):
        yield event.to_sse()
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from schemas.qa import QARequest, QAResult
from schemas.common import CausalStep, KeyTerm, SourceReference
from schemas.events import StreamEvent, EventEmitter, generate_run_id
from schemas.event_sink import EventSink, NullEventSink
from repositories.rag_repo import RAGRepository
from repositories.knowledge_repo import KnowledgeRepository
from infrastructure.llm_client import LLMClient

logger = logging.getLogger(__name__)


class QAService:
    """
    智能答疑服务。

    所有外部依赖通过构造器注入，便于测试和替换。
    与 Streamlit / FastAPI 完全解耦 — 只依赖 ABC 和 Pydantic schema。
    """

    def __init__(
        self,
        rag_repo: RAGRepository,
        knowledge_repo: KnowledgeRepository,
        llm_client: LLMClient | None = None,
    ) -> None:
        """
        Args:
            rag_repo: RAG 向量检索实现（ChromaDB 或其他）
            knowledge_repo: 知识库实现（JSON 文件 或 SQLite）
            llm_client: LLM 客户端（V1 占位，V2 接真实模型）
        """
        self.rag = rag_repo
        self.knowledge = knowledge_repo
        self.llm = llm_client

    # ── 非流式入口 ──────────────────────────────────────────

    async def answer(
        self,
        request: QARequest,
        *,
        sink: EventSink | None = None,
    ) -> QAResult:
        """
        统一答疑入口 — 非流式，返回完整 QAResult。

        如果提供 event_sink，执行过程中会推送 StreamEvent 进度事件。
        适合：Streamlit 页面直接调用，或 FastAPI 非流式端点。

        Args:
            request: QARequest (session_id, question, knowledge_id, language)
            event_sink: 可选异步回调，接收 StreamEvent

        Returns:
            QAResult — 完整结构化回答
        """
        s = sink or NullEventSink()
        emitter = EventEmitter(
            run_id=generate_run_id(),
            session_id=request.session_id,
            stage="qa",
        )

        # 1. run.started
        await s.emit(emitter.run_started(question=request.question))

        # 2. 检索阶段
        await s.emit(emitter.retrieval_started(query=request.question))

        zh_results = self.rag.retrieve(request.question, language="zh", top_k=5)
        en_results = self.rag.retrieve(request.question, language="en", top_k=5)
        image_results = self.rag.retrieve_images(request.question, language="zh", top_k=3)

        all_retrieved = zh_results + en_results
        for src in self._extract_sources(all_retrieved, image_results):
            await s.emit(emitter.retrieval_source_found(
                file_name=src.get("file_name", ""),
                chapter=src.get("chapter"),
                language=src.get("language", "zh"),
                score=src.get("score"),
                chunk_id=src.get("chunk_id"),
            ))

        total_sources = len(zh_results) + len(en_results) + len(image_results)
        await s.emit(emitter.retrieval_completed(source_count=total_sources))

        # 3. 知识图谱匹配
        graph_chain = self.knowledge.match_chain(request.question)
        chain_id = graph_chain.get("chain_id") if graph_chain else None

        # 4. 因果链
        causal_chain = self._build_causal_chain(graph_chain)

        # 5. 术语查找
        key_terms = self._build_key_terms(request.question, graph_chain)

        # 6. 误区
        misconceptions = graph_chain.get("common_misconceptions", []) if graph_chain else []

        # 7. 自测题
        self_test = self._find_self_test(chain_id, request.question)

        # 8. 教材来源
        sources = self._extract_sources(all_retrieved, image_results)

        # 9. 生成阶段（V1: 占位，V2: LLM 生成）
        await s.emit(emitter.generation_started())

        short_answer = graph_chain.get("summary", "") if graph_chain else ""
        principle = graph_chain.get("summary", "") if graph_chain else ""

        # TODO (V2): LLM 逐 section 生成，每个 delta 推 sink
        # await s.emit(emitter.generation_delta(section="short_answer", delta=...))
        # await s.emit(emitter.generation_section_completed(section="short_answer"))

        for section in ["short_answer", "principle", "causal_chain", "key_terms"]:
            await s.emit(emitter.generation_section_completed(section=section))

        # 10. 组装结果
        result = QAResult(
            question=request.question,
            knowledge_id=request.knowledge_id or "K001",
            chain_id=chain_id or "C001",
            short_answer=short_answer,
            principle=principle,
            causal_chain=[
                CausalStep(
                    node_id=step.get("node_id", f"node_{i}"),
                    label_zh=step.get("label_zh", step) if isinstance(step, dict) else str(step),
                    label_en=step.get("label_en", "") if isinstance(step, dict) else "",
                    relation=step.get("relation", "") if isinstance(step, dict) else "",
                    explanation=step.get("explanation", "") if isinstance(step, dict) else "",
                )
                for i, step in enumerate(causal_chain)
            ] if causal_chain else [],
            key_terms=[
                KeyTerm(
                    zh=t.get("zh", ""),
                    en=t.get("en", ""),
                    category=t.get("category"),
                    definition_zh=t.get("definition_zh"),
                )
                for t in key_terms
            ],
            misconceptions=misconceptions,
            recommended_question_id=self_test.get("question_id") if self_test else None,
            sources=[
                SourceReference(
                    chunk_id=s.get("chunk_id", ""),
                    file_name=s.get("file_name", ""),
                    language=s.get("language", "zh"),
                    chapter=s.get("chapter"),
                    section=s.get("section"),
                    page_start=s.get("page_start"),
                    text=s.get("text", "")[:500],
                    score=s.get("score"),
                )
                for s in sources[:10]
            ],
            prompt="",  # TODO (V2): build_constrained_qa_prompt
            retrieval_debug={
                "query": request.question,
                "zh_count": len(zh_results),
                "en_count": len(en_results),
                "image_count": len(image_results),
            },
        )

        # 11. run.completed
        await s.emit(emitter.run_completed(result=result.model_dump()))

        return result

    # ── 流式入口 ────────────────────────────────────────────

    async def answer_stream(
        self,
        request: QARequest,
    ) -> AsyncIterator[StreamEvent]:
        """
        流式答疑 — 返回 AsyncIterator[StreamEvent]。

        适合 FastAPI SSE 端点:
            async for event in service.answer_stream(request):
                yield event.to_sse()

        内部用列表收集事件，执行完后逐个 yield。
        """
        events: list[StreamEvent] = []
        collect_sink = _CollectorSink(events)
        await self.answer(request, sink=collect_sink)

        for event in events:
            yield event

    def _build_key_terms(self, query: str, graph_chain: dict | None) -> list[dict]:
        """
        合并术语来源：
          1. 查询匹配术语（通过 rag.expand_terms）
          2. 因果链节点术语（通过 knowledge.get_term 反查）
        """
        seen_zh: set[str] = set()
        merged: list[dict] = []

        # 来源 1: 术语扩展
        expanded = self.rag.expand_terms(query, language="zh")
        for term_str in expanded:
            if term_str and term_str not in seen_zh:
                seen_zh.add(term_str)
                term_info = self.knowledge.get_term(term_str, language="zh")
                if term_info:
                    merged.append({
                        "zh": term_info.get("zh", term_str),
                        "en": term_info.get("en", ""),
                        "category": term_info.get("category"),
                        "definition_zh": term_info.get("definition_zh"),
                    })
                else:
                    merged.append({"zh": term_str, "en": ""})

        # 来源 2: 因果链节点 → term_id
        if graph_chain:
            graph = self.knowledge.get_knowledge_graph()
            node_map = {n["id"]: n for n in graph.get("nodes", [])}
            path_ids = set(graph_chain.get("path", []))

            # 收集路径节点 + 邻接节点
            related_ids = set(path_ids)
            for edge in graph.get("edges", []):
                if edge.get("source") in path_ids or edge.get("target") in path_ids:
                    related_ids.add(edge.get("source", ""))
                    related_ids.add(edge.get("target", ""))

            for node_id in related_ids:
                node = node_map.get(node_id, {})
                tid = node.get("term_id", "")
                if tid:
                    term_info = self.knowledge.get_term(tid, language="zh")
                    if term_info:
                        zh = term_info.get("zh", "")
                        if zh and zh not in seen_zh:
                            seen_zh.add(zh)
                            merged.append({
                                "zh": zh,
                                "en": term_info.get("en", ""),
                                "category": term_info.get("category"),
                                "definition_zh": term_info.get("definition_zh"),
                            })

        return merged

    def _build_causal_chain(self, graph_chain: dict | None) -> list[dict]:
        """从知识图谱因果链提取节点详情"""
        if not graph_chain:
            return []

        graph = self.knowledge.get_knowledge_graph()
        node_map = {n["id"]: n for n in graph.get("nodes", [])}

        result: list[dict] = []
        for i, node_id in enumerate(graph_chain.get("path", [])):
            node = node_map.get(node_id, {})
            # 查找与前一个节点的边
            relation = ""
            if i > 0 and "edges" in graph:
                prev_id = graph_chain["path"][i - 1]
                for edge in graph["edges"]:
                    if edge.get("source") == prev_id and edge.get("target") == node_id:
                        relation = edge.get("relation", "")
                        break

            result.append({
                "node_id": node_id,
                "label_zh": node.get("label_zh", node_id),
                "label_en": node.get("label_en", ""),
                "relation": relation,
                "explanation": node.get("description", ""),
            })

        return result

    def _find_self_test(self, chain_id: str | None, query: str) -> dict | None:
        """优先按 chain_id 匹配，其次按关键词匹配"""
        all_questions = self.knowledge.list_questions()

        if chain_id:
            for q in all_questions:
                if q.get("next_chain_id") == chain_id:
                    return {
                        "question_id": q["question_id"],
                        "question": q["question"],
                        "difficulty": q.get("difficulty", ""),
                    }

        # 兜底：关键词匹配
        query_lower = query.lower()
        best_match, best_score = None, 0
        for q in all_questions:
            score = sum(
                1 for kp in q.get("knowledge_points", []) if kp.lower() in query_lower
            )
            if score > best_score:
                best_score = score
                best_match = {
                    "question_id": q["question_id"],
                    "question": q["question"],
                    "difficulty": q.get("difficulty", ""),
                }
        return best_match

    def _extract_sources(
        self,
        retrieved: list[dict],
        images: list[dict] | None = None,
        max_sources: int = 10,
    ) -> list[dict]:
        """从 RAG 结果提取去重来源列表"""
        sources: list[dict] = []
        seen: set[str] = set()

        for item in retrieved:
            meta = item.get("metadata", {})
            chunk_id = meta.get("chunk_id", "")
            if not chunk_id or chunk_id in seen:
                continue
            seen.add(chunk_id)

            headers = meta.get("headers", {})
            chapter_path = " > ".join(
                v for v in [headers.get("h1"), headers.get("h2"), headers.get("h3")] if v
            )

            sources.append({
                "chunk_id": chunk_id,
                "file_name": meta.get("file_name", ""),
                "page_start": meta.get("page"),
                "chapter": chapter_path or meta.get("chapter", ""),
                "section": headers.get("h2", ""),
                "language": meta.get("language", ""),
                "text": item.get("text", "")[:500],
                "score": item.get("distance"),
            })

            if len(sources) >= max_sources:
                break

        # 追加图片来源
        if images:
            for img in images[:3]:
                meta = img.get("metadata", {})
                chunk_id = meta.get("chunk_id", "")
                if chunk_id and chunk_id not in seen:
                    seen.add(chunk_id)
                    sources.append({
                        "chunk_id": chunk_id,
                        "file_name": meta.get("file_name", ""),
                        "chapter": meta.get("chapter", ""),
                        "language": meta.get("language", ""),
                        "text": img.get("text", "")[:200],
                        "score": img.get("distance"),
                    })

        return sources


# ═══════════════════════════════════════════════════════════
# 内部工具
# ═══════════════════════════════════════════════════════════

class _CollectorSink:
    """内部用 EventSink：将事件收集到列表中。"""
    def __init__(self, events: list[StreamEvent]) -> None:
        self.events = events

    async def emit(self, event: StreamEvent) -> None:
        self.events.append(event)


# ═══════════════════════════════════════════════════════════
# 工厂函数（Streamlit 和其他非 DI 场景使用）
# ═══════════════════════════════════════════════════════════

def create_qa_service(
    rag_repo: RAGRepository | None = None,
    knowledge_repo: KnowledgeRepository | None = None,
    llm_client: LLMClient | None = None,
) -> QAService:
    """
    创建 QAService 的便捷工厂。

    如果不传参数，自动使用默认实现（V1 文件知识库 + ChromaDB）。

    用法:
        # 生产（默认）
        service = create_qa_service()

        # Streamlit（需要同步调用，用 asyncio.run 包装）
        result = asyncio.run(service.answer(request))

        # 测试（注入 mock）
        service = create_qa_service(
            rag_repo=mock_rag,
            knowledge_repo=mock_knowledge,
        )
    """
    if rag_repo is None:
        from infrastructure.chroma_store import ChromaStore
        rag_repo = ChromaStore()

    if knowledge_repo is None:
        from infrastructure.file_knowledge_repo import FileKnowledgeRepository
        knowledge_repo = FileKnowledgeRepository()

    if llm_client is None:
        from infrastructure.llm_client import create_llm_client
        llm_client = create_llm_client()

    return QAService(
        rag_repo=rag_repo,
        knowledge_repo=knowledge_repo,
        llm_client=llm_client,
    )


# ═══════════════════════════════════════════════════════════
# 向后兼容：保留旧模块级函数签名
# ═══════════════════════════════════════════════════════════

def answer_question(user_question: str) -> dict:
    """
    DEPRECATED: 旧同步接口，内部委托给 QAService.answer()。

    保留此函数确保现有 Streamlit pages 不报错。
    新代码请用 create_qa_service() + await service.answer()。
    """
    import asyncio

    service = create_qa_service()
    request = QARequest(session_id="default", question=user_question)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 在已有的 event loop 中（如 Streamlit 的 asyncio 线程）
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, service.answer(request))
                result = future.result(timeout=120)
        else:
            result = asyncio.run(service.answer(request))
    except RuntimeError:
        result = asyncio.run(service.answer(request))

    return result.model_dump()
