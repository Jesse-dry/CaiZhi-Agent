"""
费曼学习法评价服务。

核心理念：checklist 关键词匹配 → 五维度打分 → 结构化评价结果。
V1 用关键词匹配，接入 LLM 后替换 evaluate 逻辑即可。
"""

import json
import re
from pathlib import Path

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


def _count_all_keyword_matches(text: str, checklist: list[dict]) -> int:
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
    # 长度适中
    length = len(text)
    if 80 <= length <= 600:
        score += 6
    elif 50 <= length <= 800:
        score += 3
    elif length > 0:
        score += 1
    # 有逻辑连接词
    logic_words = ["因为", "所以", "因此", "首先", "然后", "最后", "由于", "导致", "从而"]
    logic_count = sum(1 for w in logic_words if w in text)
    score += min(logic_count * 2, 6)
    # 分段/句号
    sentence_count = len(re.findall(r"[。.!！?？\n]", text))
    score += min(sentence_count, 4)
    return min(score, max_score)


def evaluate(explanation: str, feynman_id: str = "F001") -> dict:
    """
    评价学生的费曼解释。

    参数:
        explanation: 学生的解释文本
        feynman_id: 评价标准 ID

    返回:
        {
            "feynman_id": "F001",
            "total_score": int,
            "dimension_scores": {...},
            "covered_points": [...],
            "missing_points": [...],
            "incorrect_points": [...],
            "next_question": str,
        }
    """
    rubric = load_feynman_rubric(feynman_id)
    if rubric is None:
        return {
            "feynman_id": feynman_id,
            "total_score": 0,
            "dimension_scores": {},
            "covered_points": [],
            "missing_points": [],
            "incorrect_points": [],
            "next_question": "",
        }

    checklist = rubric.get("checklist", [])
    if not checklist:
        return {
            "feynman_id": feynman_id,
            "total_score": 0,
            "dimension_scores": {},
            "covered_points": [],
            "missing_points": [],
            "incorrect_points": [],
            "next_question": "",
        }

    # ── 逐条检查 checklist ──
    covered_points: list[str] = []
    missing_points: list[str] = []
    dim_scores: dict[str, int] = {
        "concept_accuracy": 0,
        "causal_completeness": 0,
        "term_accuracy": 0,
        "clarity": 0,
        "misconception_control": 10,  # V1 默认满分，LLM 接入后真实评分
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

    # ── 术语准确性：匹配到的关键词比例 ──
    matched_kw, total_kw = _count_all_keyword_matches(explanation, checklist)
    if total_kw > 0:
        dim_scores["term_accuracy"] = round(matched_kw / total_kw * 14)

    # ── 表达清晰度 ──
    dim_scores["clarity"] = _score_clarity(explanation)

    # ── 总分 ──
    total_score = sum(dim_scores.values())

    # ── 生成后续问题（基于第一个缺失点） ──
    next_question = ""
    for idx, dim_key, _ in _CHECKLIST_DIM_MAP:
        if idx >= len(checklist):
            continue
        item = checklist[idx]
        if item.get("point", "") in missing_points:
            next_question = _FOLLOWUP_QUESTIONS.get(idx, "")
            break

    # ── incorrect_points（V1 无法检测，LLM 接入后启用） ──
    incorrect_points: list[str] = []

    return {
        "feynman_id": feynman_id,
        "total_score": total_score,
        "dimension_scores": {
            "concept_accuracy": dim_scores["concept_accuracy"],
            "causal_completeness": dim_scores["causal_completeness"],
            "term_accuracy": dim_scores["term_accuracy"],
            "clarity": dim_scores["clarity"],
            "misconception_control": dim_scores["misconception_control"],
        },
        "covered_points": covered_points,
        "missing_points": missing_points,
        "incorrect_points": incorrect_points,
        "next_question": next_question,
    }
