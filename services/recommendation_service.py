"""
学习路径推荐服务。

规则驱动，聚合四个输入源：
  1. 错题诊断 → missing_concepts
  2. 苏格拉底引导 → remaining_weak_points
  3. 费曼评价 → missing_points
  4. 知识图谱 → 先修关系

V1 纯规则映射，V2 用 GraphReasoningAgent 推理缺失先修和因果断裂。

V2：返回 ServiceResult[LearningPathResult]，统一错误处理。
向后兼容：generate_learning_path_legacy() 返回旧 dict。
"""

import logging
from collections import OrderedDict
from datetime import datetime, UTC

from schemas.recommendation import (
    LearningPathResult, WeakPointDetail, RecommendedStep,
)
from schemas.common import MasteryLevel, ServiceResult
from schemas.agent import create_agent_context

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 知识单元定义（V1 硬编码，后续可从配置文件加载）
# ═══════════════════════════════════════════════════════════

KNOWLEDGE_UNITS: dict[str, dict] = OrderedDict({
    "K001": {
        "title": "淬火与硬度关系",
        "description": "理解淬火工艺如何通过组织转变提高钢的硬度",
        "prerequisites": [],
        "keywords": ["淬火", "硬度", "快速冷却"],
    },
    "K004": {
        "title": "珠光体与马氏体对比",
        "description": "先区分珠光体和马氏体",
        "prerequisites": ["K001"],
        "keywords": ["珠光体", "马氏体", "扩散", "无扩散相变", "冷却速度"],
    },
    "K002": {
        "title": "马氏体组织结构",
        "description": "理解马氏体硬而脆的结构原因",
        "prerequisites": ["K001"],
        "keywords": ["马氏体", "晶格畸变", "过饱和碳", "位错运动", "碳原子"],
    },
    "K003": {
        "title": "回火工艺与原理",
        "description": "继续学习为什么淬火后需要回火",
        "prerequisites": ["K002", "K004"],
        "keywords": ["回火", "韧性", "马氏体分解", "内应力", "脆性"],
    },
})


# ═══════════════════════════════════════════════════════════
# 内部工具
# ═══════════════════════════════════════════════════════════

def _deduplicate(items: list[str]) -> list[str]:
    """去重保序"""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _collect_weak_points(
    diagnosis_result: dict | None,
    socratic_result: dict | None,
    feynman_result: dict | None,
) -> list[str]:
    """从三个来源聚合薄弱知识点"""
    raw: list[str] = []

    if diagnosis_result:
        raw.extend(diagnosis_result.get("missing_concepts", []))
        misc = diagnosis_result.get("misconception", "")
        if misc:
            raw.append(misc)

    if socratic_result:
        raw.extend(socratic_result.get("remaining_weak_points", []))

    if feynman_result:
        raw.extend(feynman_result.get("missing_points", []))

    return _deduplicate(raw)


def _map_weak_points_to_units(weak_points: list[str]) -> list[str]:
    """将薄弱点关键词映射到知识单元 ID"""
    matched_units: set[str] = set()

    for point in weak_points:
        point_lower = point.lower()
        best_unit = None
        best_score = 0
        for unit_id, unit in KNOWLEDGE_UNITS.items():
            if unit_id in matched_units:
                continue
            score = sum(
                1 for kw in unit.get("keywords", [])
                if kw.lower() in point_lower
            )
            if score > best_score:
                best_score = score
                best_unit = unit_id

        if best_unit:
            matched_units.add(best_unit)
        else:
            matched_units.add("K001")

    return list(matched_units)


def _sort_by_prerequisites(unit_ids: list[str]) -> list[str]:
    """按先修关系拓扑排序"""
    all_ids = set(unit_ids)
    sorted_ids: list[str] = []
    remaining = set(unit_ids)

    while remaining:
        ready = []
        for uid in sorted(remaining, key=lambda x: list(KNOWLEDGE_UNITS.keys()).index(x)):
            prereqs = KNOWLEDGE_UNITS.get(uid, {}).get("prerequisites", [])
            relevant_prereqs = [p for p in prereqs if p in all_ids]
            if all(p in sorted_ids for p in relevant_prereqs):
                ready.append(uid)

        if ready:
            sorted_ids.extend(ready)
            remaining -= set(ready)
        else:
            sorted_ids.extend(sorted(remaining, key=lambda x: list(KNOWLEDGE_UNITS.keys()).index(x)))
            break

    return sorted_ids


def _determine_level(weak_points: list[str]) -> MasteryLevel:
    """根据薄弱点数量判断掌握程度"""
    count = len(weak_points)
    if count == 0:
        return MasteryLevel.MASTERED
    elif count <= 2:
        return MasteryLevel.BASIC
    elif count <= 5:
        return MasteryLevel.PARTIAL
    else:
        return MasteryLevel.NEEDS_IMPROVEMENT


def _trace_source(point: str, diagnosis: dict | None, socratic: dict | None, feynman: dict | None) -> str:
    """追溯薄弱点来源"""
    sources = []
    if diagnosis:
        if point in diagnosis.get("missing_concepts", []) or point == diagnosis.get("misconception", ""):
            sources.append("diagnosis")
    if socratic:
        if point in socratic.get("remaining_weak_points", []):
            sources.append("socratic")
    if feynman:
        if point in feynman.get("missing_points", []):
            sources.append("feynman")
    return sources[0] if sources else "system"


def _map_point_to_knowledge_id(point: str) -> str:
    """将单个薄弱点映射到知识单元 ID"""
    point_lower = point.lower()
    best_unit = None
    best_score = 0
    for unit_id, unit in KNOWLEDGE_UNITS.items():
        score = sum(1 for kw in unit.get("keywords", []) if kw.lower() in point_lower)
        if score > best_score:
            best_score = score
            best_unit = unit_id
    return best_unit or "K001"


# ═══════════════════════════════════════════════════════════
# 新版：返回 ServiceResult[LearningPathResult]
# ═══════════════════════════════════════════════════════════

def generate_learning_path(
    diagnosis_result: dict | None = None,
    socratic_result: dict | None = None,
    feynman_result: dict | None = None,
    llm_client=None,
) -> ServiceResult[LearningPathResult]:
    """
    聚合三个来源的薄弱点 → 映射知识单元 → 按先修关系排序 → 生成推荐路径。

    V2：可选 GraphReasoningAgent 推理缺失先修节点。

    返回:
        ServiceResult[LearningPathResult]
    """
    # 1. 聚合薄弱点
    weak_points = _collect_weak_points(diagnosis_result, socratic_result, feynman_result)

    # 兜底：无薄弱点时用默认值
    if not weak_points:
        weak_points = ["淬火", "马氏体", "晶格畸变"]

    # ── V2: LLM Graph Reasoning ──
    graph_causal_gaps: list[str] = []
    graph_missing_prereqs: list[str] = []
    if llm_client is not None:
        try:
            graph_insights = _reason_with_agent(llm_client, weak_points)
            if graph_insights:
                graph_causal_gaps = graph_insights.get("causal_gaps", [])
                graph_missing_prereqs = graph_insights.get("missing_prerequisites", [])
        except Exception as e:
            logger.warning(f"GraphReasoningAgent failed, using V1 mapping: {e}")

    # 2. 映射到知识单元
    unit_ids = _map_weak_points_to_units(weak_points)

    # 补充 Agent 发现的缺失先修节点
    for prereq in graph_missing_prereqs:
        if prereq in KNOWLEDGE_UNITS and prereq not in unit_ids:
            unit_ids.append(prereq)

    # 确保 K001 始终在推荐中
    if "K001" not in unit_ids and len(unit_ids) < 3:
        unit_ids.insert(0, "K001")

    # 3. 按先修关系排序
    sorted_ids = _sort_by_prerequisites(unit_ids)

    # 4. 生成推荐步骤
    recommended_steps: list[RecommendedStep] = []
    for order, uid in enumerate(sorted_ids, start=1):
        unit = KNOWLEDGE_UNITS.get(uid, {})
        recommended_steps.append(RecommendedStep(
            order=order,
            knowledge_id=uid,
            title=unit.get("title", uid),
            reason=unit.get("description", ""),
            source="system",  # 默认，下面细化
        ))

    # 5. 判断掌握程度
    current_level = _determine_level(weak_points)

    # 6. 构建 WeakPointDetail 列表（带来源追踪 + causal gaps）
    weak_point_details: list[WeakPointDetail] = []
    for point in weak_points:
        source = _trace_source(point, diagnosis_result, socratic_result, feynman_result)
        mapped_id = _map_point_to_knowledge_id(point)
        weak_point_details.append(WeakPointDetail(
            point=point,
            source=source,
            mapped_knowledge_id=mapped_id,
        ))

    # 追加 GraphReasoningAgent 发现的因果断裂
    for gap in graph_causal_gaps:
        if gap and gap not in [w.point for w in weak_point_details]:
            weak_point_details.append(WeakPointDetail(
                point=gap,
                source="graph_reasoning",
                mapped_knowledge_id=_map_point_to_knowledge_id(gap),
            ))

    result = LearningPathResult(
        current_level=current_level,
        weak_points=weak_point_details,
        recommended_steps=recommended_steps,
        total_weak_points=len(weak_point_details),
        total_recommended_steps=len(recommended_steps),
        generated_at=datetime.now(UTC).isoformat(),
    )

    return ServiceResult(success=True, result=result)


# ═══════════════════════════════════════════════════════════
# LLM Agent 集成
# ═══════════════════════════════════════════════════════════

def _reason_with_agent(llm_client, weak_points: list[str]) -> dict | None:
    """Use GraphReasoningAgent to find missing prerequisites and causal gaps."""
    import asyncio
    from agents.graph_reasoning_agent import GraphReasoningAgent

    # Build graph nodes from KNOWLEDGE_UNITS (V1 hardcoded)
    graph_nodes = [
        {"id": uid, "label_zh": info.get("title", uid), "description": info.get("description", "")}
        for uid, info in KNOWLEDGE_UNITS.items()
    ]
    graph_edges = []
    for uid, info in KNOWLEDGE_UNITS.items():
        for prereq in info.get("prerequisites", []):
            graph_edges.append({
                "source": prereq,
                "target": uid,
                "relation": "requires",
            })

    agent_ctx = create_agent_context(
        session_id="recommendation",
        student_input="",
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        metadata={"weak_points": weak_points},
    )

    agent = GraphReasoningAgent(llm_client)
    agent_result = _run_async(agent.run(agent_ctx))

    if not agent_result or not agent_result.structured_data:
        return None

    return agent_result.structured_data


def _run_async(coro):
    """Run an async coroutine in a sync-compatible way."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result(timeout=60)
        return asyncio.run(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════
# 向后兼容 wrapper — 返回 dict
# ═══════════════════════════════════════════════════════════

def generate_learning_path_legacy(
    diagnosis_result: dict | None = None,
    socratic_result: dict | None = None,
    feynman_result: dict | None = None,
) -> dict:
    """
    [deprecated] 旧 dict 接口，内部委托给 generate_learning_path()。

    Streamlit 页面在 Phase 3 迁移前继续使用此函数。
    """
    sr = generate_learning_path(diagnosis_result, socratic_result, feynman_result)
    if sr.success and sr.result:
        r = sr.result
        return {
            "current_level": r.current_level.value,
            "weak_points": [w.point for w in r.weak_points],
            "recommended_steps": [
                {"order": s.order, "knowledge_id": s.knowledge_id, "reason": s.reason, "title": s.title}
                for s in r.recommended_steps
            ],
        }
    return {
        "current_level": "需要加强",
        "weak_points": [],
        "recommended_steps": [],
    }
