"""
费曼学习法评价服务。

核心理念：checklist 关键词匹配 → 五维度打分 → 结构化评价结果。
V1 用关键词匹配，V2 用 LLM Agent 替代 evaluate 逻辑。

V2：返回 ServiceResult[FeynmanResult]，统一错误处理。
向后兼容：evaluate_legacy() 返回旧 dict 格式。
"""

import json
import logging
import re
from pathlib import Path

from schemas.feynman import FeynmanResult, DimensionScores
from schemas.common import ServiceResult, ServiceError, ServiceErrorType
from schemas.agent import create_agent_context

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
FEYNMAN_PATH = BASE_DIR / "data" / "feynman.json"


# ═══════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════

def load_feynman_rubric(feynman_id: str) -> dict | None:
    """加载指定 ID 的费曼评价标准"""
    with open(FEYNMAN_PATH, "r", encoding="utf-8") as f:
        rubrics = json.load(f)
    for r in rubrics:
        if r.get("feynman_id") == feynman_id:
            return r
    return None


# ═══════════════════════════════════════════════════════════
# 评价引擎
# ═══════════════════════════════════════════════════════════

# checklist 中每一条对应哪个维度及其分值
_CHECKLIST_DIM_MAP: list[tuple[int, str, int]] = [
    (0, "concept_accuracy", 9),       # "指出淬火的核心是快速冷却"
    (1, "concept_accuracy", 9),       # "说明快速冷却会抑制碳原子扩散"
    (2, "causal_completeness", 5),    # "说明奥氏体会转变为马氏体"
    (3, "causal_completeness", 5),    # "说明马氏体产生晶格畸变"
    (4, "causal_completeness", 5),    # "说明晶格畸变阻碍位错运动"
    (5, "causal_completeness", 5),    # "最终连接到硬度提高"
]

# 后续问题模板：每个 checklist 点对应的追问
_FOLLOWUP_QUESTIONS: dict[int, str] = {
    0: "快速冷却和缓慢冷却得到的组织有什么不同？",
    1: "碳原子扩散受到抑制后，奥氏体中的碳会去哪里？",
    2: "奥氏体和马氏体的晶体结构有什么区别？",
    3: "马氏体中的过饱和碳如何影响晶格结构？",
    4: "晶格畸变为什么会使钢更难发生塑性变形？",
    5: "除了硬度，淬火还会影响钢的哪些性能？",
}


def _match_keywords(text: str, keywords: list[str]) -> bool:
    """检查文本中是否包含任意一个关键词"""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _count_all_keyword_matches(text: str, checklist: list[dict]) -> tuple[int, int]:
    """统计所有 checklist 条目中匹配到的关键词总数"""
    text_lower = text.lower()
    all_keywords = set()
    matched = set()
    for item in checklist:
        for kw in item.get("keywords", []):
            all_keywords.add(kw.lower())
            if kw.lower() in text_lower:
                matched.add(kw.lower())
    return len(matched), len(all_keywords)


def _score_clarity(text: str, max_score: int = 16) -> int:
    """基于文本结构估算表达清晰度（V1 简单启发式）"""
    score = 0
    length = len(text)
    if 80 <= length <= 600:
        score += 6
    elif 50 <= length <= 800:
        score += 3
    elif length > 0:
        score += 1
    logic_words = ["因为", "所以", "因此", "首先", "然后", "最后", "由于", "导致", "从而"]
    logic_count = sum(1 for w in logic_words if w in text)
    score += min(logic_count * 2, 6)
    sentence_count = len(re.findall(r"[。.!！?？\n]", text))
    score += min(sentence_count, 4)
    return min(score, max_score)


# ═══════════════════════════════════════════════════════════
# 新版：返回 ServiceResult[FeynmanResult]
# ═══════════════════════════════════════════════════════════

def evaluate(explanation: str, feynman_id: str = "F001", llm_client=None) -> ServiceResult[FeynmanResult]:
    """
    评价学生的费曼解释。

    V2：LLM Agent 评价（V1 关键词 fallback）。

    参数:
        explanation: 学生的解释文本
        feynman_id: 评价标准 ID
        llm_client: 可选 LLM 客户端，用于 AI 评价

    返回:
        ServiceResult[FeynmanResult]
    """
    rubric = load_feynman_rubric(feynman_id)
    if rubric is None:
        return ServiceResult(
            success=False,
            errors=[ServiceError(
                type=ServiceErrorType.KNOWLEDGE_NOT_FOUND,
                message=f"未找到费曼评价标准：{feynman_id}",
            )],
        )

    # ── V2: LLM Agent ──
    if llm_client is not None:
        try:
            agent_result = _evaluate_with_agent(llm_client, explanation, rubric)
            if agent_result is not None:
                return agent_result
        except Exception as e:
            logger.warning(f"FeynmanAgent failed, falling back to V1 keyword: {e}")

    # ── V1: keyword-based fallback ──
    checklist = rubric.get("checklist", [])
    if not checklist:
        return ServiceResult(
            success=False,
            errors=[ServiceError(
                type=ServiceErrorType.KNOWLEDGE_NOT_FOUND,
                message=f"评价标准 {feynman_id} 的 checklist 为空",
            )],
        )

    covered_points: list[str] = []
    missing_points: list[str] = []
    dim_scores: dict[str, int] = {
        "concept_accuracy": 0,
        "causal_completeness": 0,
        "term_accuracy": 0,
        "clarity": 0,
        "misconception_control": 10,  # V1 默认满分
    }

    for idx, dim_key, max_pts in _CHECKLIST_DIM_MAP:
        if idx >= len(checklist):
            continue
        item = checklist[idx]
        keywords = item.get("keywords", [])
        point_label = item.get("point", "")

        if _match_keywords(explanation, keywords):
            covered_points.append(point_label)
            dim_scores[dim_key] += max_pts
        else:
            missing_points.append(point_label)

    # ── 术语准确性 ──
    matched_kw, total_kw = _count_all_keyword_matches(explanation, checklist)
    if total_kw > 0:
        dim_scores["term_accuracy"] = round(matched_kw / total_kw * 14)

    # ── 表达清晰度 ──
    dim_scores["clarity"] = _score_clarity(explanation)

    # ── 总分 ──
    total_score = sum(dim_scores.values())

    # ── 生成后续问题 ──
    next_question = ""
    for idx, dim_key, _ in _CHECKLIST_DIM_MAP:
        if idx >= len(checklist):
            continue
        item = checklist[idx]
        if item.get("point", "") in missing_points:
            next_question = _FOLLOWUP_QUESTIONS.get(idx, "")
            break

    result = FeynmanResult(
        feynman_id=feynman_id,
        total_score=total_score,
        dimension_scores=DimensionScores(
            concept_accuracy=dim_scores["concept_accuracy"],
            causal_completeness=dim_scores["causal_completeness"],
            term_accuracy=dim_scores["term_accuracy"],
            clarity=dim_scores["clarity"],
            misconception_control=dim_scores["misconception_control"],
        ),
        covered_points=covered_points,
        missing_points=missing_points,
        incorrect_points=[],  # V1 无法检测，V2 LLM 接入后启用
        next_question=next_question,
    )

    return ServiceResult(success=True, result=result)


# ═══════════════════════════════════════════════════════════
# LLM Agent 集成
# ═══════════════════════════════════════════════════════════

def _evaluate_with_agent(llm_client, explanation: str, rubric: dict) -> ServiceResult[FeynmanResult] | None:
    """Use FeynmanAgent to evaluate the explanation via LLM."""
    import asyncio
    from agents.feynman_agent import FeynmanAgent

    feynman_id = rubric.get("feynman_id", "F001")

    agent_ctx = create_agent_context(
        session_id="feynman",
        student_input=explanation,
        feynman_rubric=rubric,
        metadata={"feynman_id": feynman_id},
    )

    agent = FeynmanAgent(llm_client)
    agent_result = _run_async(agent.run(agent_ctx))

    if not agent_result or not agent_result.structured_data:
        return None

    sd = agent_result.structured_data
    dim_scores = sd.get("dimension_scores", {})

    result = FeynmanResult(
        feynman_id=feynman_id,
        total_score=sd.get("total_score", 0),
        dimension_scores=DimensionScores(
            concept_accuracy=dim_scores.get("concept_accuracy", 0),
            causal_completeness=dim_scores.get("causal_completeness", 0),
            term_accuracy=dim_scores.get("term_accuracy", 0),
            clarity=dim_scores.get("clarity", 0),
            misconception_control=dim_scores.get("misconception_control", 0),
        ),
        covered_points=sd.get("covered_points", []),
        missing_points=sd.get("missing_points", []),
        incorrect_points=sd.get("incorrect_points", []),
        next_question=sd.get("next_question", ""),
    )
    return ServiceResult(success=True, result=result)


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

def evaluate_legacy(explanation: str, feynman_id: str = "F001") -> dict:
    """
    [deprecated] 旧 dict 接口，内部委托给 evaluate()。

    Streamlit 页面在 Phase 3 迁移前继续使用此函数。
    """
    sr = evaluate(explanation, feynman_id)
    if sr.success and sr.result:
        return sr.result.model_dump()
    return {
        "feynman_id": feynman_id,
        "total_score": 0,
        "dimension_scores": {},
        "covered_points": [],
        "missing_points": [],
        "incorrect_points": [],
        "next_question": "",
    }
