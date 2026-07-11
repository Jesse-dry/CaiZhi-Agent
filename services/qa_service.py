"""
统一答疑服务入口。

职责：组合四个数据源 → 构建约束型回答 → 返回结构化 dict。
四个数据源各有边界，互不越界：
  1. 教材 RAG     → 事实依据（定义、原理、组织转变、性能变化）
  2. knowledge_graph → 因果链路径
  3. terms.csv    → 术语标准翻译（禁止 LLM 自造）
  4. questions.json → 自测题匹配（禁止 LLM 临时出题）
"""

import json
from pathlib import Path

import pandas as pd

from services.rag_service import search_textbooks
from knowledge.knowledge_graph import match_chain, load_knowledge_graph
from knowledge.prompt_builder import build_constrained_qa_prompt

BASE_DIR = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = BASE_DIR / "data" / "questions.json"
TERMS_PATH = BASE_DIR / "data" / "terms.csv"


# ═══════════════════════════════════════════════════════════
# 内部工具函数
# ═══════════════════════════════════════════════════════════

def _load_questions() -> list[dict]:
    with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_terms_df() -> pd.DataFrame:
    return pd.read_csv(TERMS_PATH)


def _get_chain_node_term_ids(graph_chain: dict | None) -> list[str]:
    """从因果链的路径节点 + 邻接节点中提取所有 term_id"""
    if not graph_chain:
        return []
    graph = load_knowledge_graph()
    node_map = {n["id"]: n for n in graph.get("nodes", [])}

    # 链路径中的节点
    path_ids = set(graph_chain.get("path", []))
    # 收集所有相关节点：路径节点 + 与路径节点有边相连的节点
    related_ids = set(path_ids)
    for edge in graph.get("edges", []):
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in path_ids or tgt in path_ids:
            related_ids.add(src)
            related_ids.add(tgt)

    term_ids = []
    for node_id in related_ids:
        node = node_map.get(node_id, {})
        tid = node.get("term_id", "")
        if tid:
            term_ids.append(tid)
    return term_ids


def _lookup_terms_by_ids(terms_df: pd.DataFrame, term_ids: list[str]) -> list[dict]:
    """在 terms.csv 中按 term_id 精确查找"""
    result = []
    for tid in term_ids:
        row = terms_df[terms_df["term_id"] == tid]
        if not row.empty:
            r = row.iloc[0]
            result.append({
                "zh": str(r.get("zh", "")).strip(),
                "en": str(r.get("en", "")).strip(),
                "definition_zh": str(r.get("definition_zh", "")).strip(),
                "category": str(r.get("category", "")).strip(),
            })
    return result


def _build_key_terms(
    matched_terms: list[dict],
    graph_chain: dict | None,
) -> list[dict]:
    """
    合并两个术语来源，去重：
      1. 查询中匹配到的术语（来自 term_expander）
      2. 因果链节点对应的术语（来自 terms.csv）
    统一输出 {zh, en} 格式。
    """
    terms_df = _load_terms_df()
    seen_zh: set[str] = set()
    merged: list[dict] = []

    # 来源 1：查询匹配
    for t in matched_terms:
        zh = t.get("zh", "")
        if zh and zh not in seen_zh:
            seen_zh.add(zh)
            merged.append({"zh": zh, "en": t.get("en", "")})

    # 来源 2：因果链节点 → terms.csv
    chain_term_ids = _get_chain_node_term_ids(graph_chain)
    chain_terms = _lookup_terms_by_ids(terms_df, chain_term_ids)
    for t in chain_terms:
        zh = t.get("zh", "")
        if zh and zh not in seen_zh:
            seen_zh.add(zh)
            merged.append({"zh": zh, "en": t.get("en", "")})

    return merged


def _find_self_test(chain_id: str | None, query: str) -> dict | None:
    """优先按 chain_id 精确匹配，其次按知识点关键词匹配"""
    questions = _load_questions()

    if chain_id:
        for q in questions:
            if q.get("next_chain_id") == chain_id:
                return {
                    "question_id": q["question_id"],
                    "question": q["question"],
                    "difficulty": q.get("difficulty", ""),
                }

    # 兜底关键词
    query_lower = query.lower()
    best_match, best_score = None, 0
    for q in questions:
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


def _extract_sources(rag_result: dict, max_sources: int = 10) -> list[dict]:
    """从 RAG 检索结果提取教材来源，中文优先，按 chunk_id 去重"""
    sources: list[dict] = []
    seen: set[str] = set()

    for ctx_type in ["zh_contexts", "en_contexts"]:
        for item in rag_result.get(ctx_type, []):
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
                "file_name": meta.get("file_name", ""),
                "page": meta.get("page", 0),
                "chapter": chapter_path or meta.get("chapter", ""),
                "language": meta.get("language", ""),
                "text": item.get("text", "")[:500],
            })

            if len(sources) >= max_sources:
                return sources
    return sources


def _build_causal_chain(graph_chain: dict | None) -> list[str]:
    """从知识图谱因果链中提取 label_zh 路径列表"""
    if not graph_chain:
        return []

    graph = load_knowledge_graph()
    node_map = {n["id"]: n for n in graph.get("nodes", [])}

    labels: list[str] = []
    for node_id in graph_chain.get("path", []):
        node = node_map.get(node_id)
        labels.append(node.get("label_zh", node_id) if node else node_id)
    return labels


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

def answer_question(user_question: str) -> dict:
    """
    统一答疑入口 —— 页面只需调用这一个函数。

    返回:
        {
            "question", "chain_id",
            "short_answer", "principle",        # TODO: LLM 生成
            "causal_chain", "key_terms",
            "misconceptions", "self_test",
            "sources", "prompt", "retrieval_debug",
        }
    """
    # ── 1. 双语教材检索 ──
    rag_result = search_textbooks(user_question, top_k_each=5)

    # ── 2. 知识图谱因果链 ──
    graph_chain = match_chain(user_question)
    chain_id = graph_chain.get("chain_id") if graph_chain else None

    # ── 3. 因果链路径 ──
    causal_chain = _build_causal_chain(graph_chain)

    # ── 4. 关键术语（查询匹配 + 因果链节点反查 terms.csv） ──
    key_terms = _build_key_terms(
        matched_terms=rag_result.get("matched_terms", []),
        graph_chain=graph_chain,
    )

    # ── 5. 常见误区（来自知识图谱） ──
    misconceptions = graph_chain.get("common_misconceptions", []) if graph_chain else []

    # ── 6. 自测题（来自 questions.json，不是 LLM 临时出题） ──
    self_test = _find_self_test(chain_id, user_question)

    # ── 7. 教材来源 ──
    sources = _extract_sources(rag_result)

    # ── 8. 构建约束型 LLM prompt ──
    # 四个数据源组合在一起，各自有明确的职责边界
    prompt = build_constrained_qa_prompt(
        user_question=user_question,
        zh_contexts=rag_result.get("zh_contexts", []),
        en_contexts=rag_result.get("en_contexts", []),
        image_contexts=rag_result.get("image_contexts", []),
        causal_chain=causal_chain,
        key_terms=key_terms,
        misconceptions=misconceptions,
        self_test=self_test,
        sources=sources,
    )

    # ── 9. 简明回答 & 原理（TODO: 接入 LLM，用 prompt 生成） ──
    placeholder_answer = graph_chain.get("summary", "") if graph_chain else ""
    placeholder_principle = graph_chain.get("summary", "") if graph_chain else ""

    return {
        "question": user_question,
        "chain_id": chain_id or "C001",
        "short_answer": placeholder_answer,
        "principle": placeholder_principle,
        "causal_chain": causal_chain,
        "key_terms": key_terms,
        "misconceptions": misconceptions,
        "self_test": self_test,
        "sources": sources,
        "prompt": prompt,
        "retrieval_debug": {
            "zh_query": rag_result.get("zh_query", user_question),
            "en_query": rag_result.get("en_query", user_question),
            "matched_terms": rag_result.get("matched_terms", []),
        },
    }
