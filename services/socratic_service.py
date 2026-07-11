"""
苏格拉底引导服务层。

核心理念：预定义教学台阶 + 关键词匹配判断回答质量 → 决定推进/提示/重问。
V1 用关键词匹配，接入 LLM 后替换 judge 逻辑即可。
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SOCRATIC_PATH = BASE_DIR / "data" / "socratic.json"


# ═══════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════

def load_socratic_chain(socratic_id: str) -> dict | None:
    """加载指定 ID 的苏格拉底引导链"""
    with open(SOCRATIC_PATH, "r", encoding="utf-8") as f:
        chains = json.load(f)
    for chain in chains:
        if chain.get("socratic_id") == socratic_id:
            return chain
    return None


def get_step(chain: dict, step_index: int) -> dict | None:
    """获取第 N 步（1-indexed）"""
    steps = chain.get("steps", [])
    for s in steps:
        if s.get("step") == step_index:
            return s
    return None


def get_total_steps(chain: dict) -> int:
    return len(chain.get("steps", []))


# ═══════════════════════════════════════════════════════════
# 回答质量判断（V1：关键词匹配）
# ═══════════════════════════════════════════════════════════

def judge_answer(
    step: dict,
    student_answer: str,
    attempt_count: int,
) -> dict:
    """
    判断学生回答质量，返回结构化 step result。

    参数:
        step: 当前教学台阶（含 question, expected_keywords, hint, explanation_if_wrong）
        student_answer: 学生的回答文本
        attempt_count: 当前台阶的尝试次数（1-based）

    返回:
        {
            "step_id": int,
            "student_answer_quality": "complete" | "partial" | "incorrect",
            "covered_points": [...],
            "missing_points": [...],
            "action": "advance" | "hint" | "retry" | "simplify" | "complete",
            "response": str,
        }
    """
    step_id = step.get("step", 0)
    expected = step.get("expected_keywords", [])
    hint = step.get("hint", "")
    explanation = step.get("explanation_if_wrong", "")

    answer_lower = student_answer.lower()

    # 关键词匹配
    covered = [kw for kw in expected if kw.lower() in answer_lower]
    missing = [kw for kw in expected if kw.lower() not in answer_lower]

    total = len(expected)
    matched = len(covered)
    ratio = matched / total if total > 0 else 0

    # ── 判断质量 ──
    if ratio >= 0.75:
        quality = "complete"
    elif ratio > 0:
        quality = "partial"
    else:
        quality = "incorrect"

    # ── 决定 action ──
    if quality == "complete":
        action = "advance"
        response = _build_advance_response(covered)
    elif quality == "partial":
        if attempt_count >= 3:
            action = "simplify"
            response = _build_simplify_response(missing, explanation)
        else:
            action = "hint"
            response = _build_hint_response(covered, missing, hint)
    else:  # incorrect
        if attempt_count >= 3:
            action = "simplify"
            response = _build_simplify_response(missing, explanation)
        else:
            action = "retry"
            response = _build_retry_response(explanation)

    return {
        "step_id": step_id,
        "student_answer_quality": quality,
        "covered_points": covered,
        "missing_points": missing,
        "action": action,
        "response": response,
    }


def complete_socratic(
    socratic_id: str,
    covered_points: list[str],
    weak_points: list[str],
) -> dict:
    """生成苏格拉底引导完成结果"""
    chain = load_socratic_chain(socratic_id)
    summary = chain.get("final_summary", "") if chain else ""

    return {
        "socratic_id": socratic_id,
        "completed": True,
        "covered_points": covered_points,
        "remaining_weak_points": weak_points,
        "summary": summary,
    }


# ═══════════════════════════════════════════════════════════
# 内部：response 构建
# ═══════════════════════════════════════════════════════════

def _build_advance_response(covered: list[str]) -> str:
    points = "、".join(covered)
    return f"很好！你已经提到了：{points}。我们继续下一步。"


def _build_hint_response(covered: list[str], missing: list[str], hint: str) -> str:
    parts = []
    if covered:
        parts.append(f"你已经想到了：{'、'.join(covered)}。")
    if missing:
        parts.append(f"再想想：{'、'.join(missing)}？")
    if hint:
        parts.append(f"💡 {hint}")
    return "\n\n".join(parts)


def _build_retry_response(explanation: str) -> str:
    return f"还不太对。{explanation}\n\n请再试一次。"


def _build_simplify_response(missing: list[str], explanation: str) -> str:
    missing_str = "、".join(missing) if missing else "这个知识点"
    return (
        f"我们换个方式理解。{missing_str}：{explanation}\n\n"
        f"现在请用自己的话复述一遍。"
    )
