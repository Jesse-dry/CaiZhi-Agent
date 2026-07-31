"""
苏格拉底引导服务层。

核心理念：预定义教学台阶 + LLM Agent 判断回答质量 → 决定推进/提示/重问。
V1 用关键词匹配（fallback），V2 用 LLM Agent。

V2：返回 ServiceResult[SocraticStepResult] / ServiceResult[SocraticCompleteResult]。
向后兼容：judge_answer_legacy() / complete_socratic_legacy() 返回旧 dict。
"""

import json
import logging
from pathlib import Path

from schemas.socratic import SocraticStepResult, SocraticCompleteResult
from schemas.common import (
    AnswerQuality, SocraticAction,
    ServiceResult, ServiceError, ServiceErrorType,
)
from schemas.agent import create_agent_context

logger = logging.getLogger(__name__)

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


# ═══════════════════════════════════════════════════════════
# 新版：返回 ServiceResult
# ═══════════════════════════════════════════════════════════

def judge_answer(
    step: dict,
    student_answer: str,
    attempt_count: int,
    llm_client=None,
    socratic_chain: dict | None = None,
) -> ServiceResult[SocraticStepResult]:
    """
    判断学生回答质量，返回 ServiceResult[SocraticStepResult]。

    V2：LLM Agent 判断（V1 关键词 fallback）。

    参数:
        step: 当前教学台阶（含 question, expected_keywords, hint, explanation_if_wrong）
        student_answer: 学生的回答文本
        attempt_count: 当前台阶的尝试次数（1-based）
        llm_client: 可选 LLM 客户端
        socratic_chain: 可选完整苏格拉底链（Agent 需要完整上下文）
    """
    step_id = step.get("step", 0)

    # ── V2: LLM Agent ──
    if llm_client is not None:
        try:
            result = _judge_with_agent(
                llm_client, step, student_answer, attempt_count, socratic_chain
            )
            if result is not None:
                return result
        except Exception as e:
            logger.warning(f"SocraticAgent failed, falling back to V1 keyword: {e}")

    # ── V1: keyword fallback ──
    expected = step.get("expected_keywords", [])
    hint = step.get("hint", "")
    explanation = step.get("explanation_if_wrong", "")

    if not expected:
        return ServiceResult(
            success=False,
            errors=[ServiceError(
                type=ServiceErrorType.KNOWLEDGE_NOT_FOUND,
                message=f"步骤 {step_id} 缺少 expected_keywords",
            )],
        )

    answer_lower = student_answer.lower()

    # 关键词匹配
    covered = [kw for kw in expected if kw.lower() in answer_lower]
    missing = [kw for kw in expected if kw.lower() not in answer_lower]

    total = len(expected)
    matched = len(covered)
    ratio = matched / total if total > 0 else 0

    # ── 判断质量 ──
    if ratio >= 0.75:
        quality = AnswerQuality.COMPLETE
    elif ratio > 0:
        quality = AnswerQuality.PARTIAL
    else:
        quality = AnswerQuality.INCORRECT

    # ── 决定 action ──
    if quality == AnswerQuality.COMPLETE:
        action = SocraticAction.ADVANCE
        response = _build_advance_response(covered)
    elif quality == AnswerQuality.PARTIAL:
        if attempt_count >= 3:
            action = SocraticAction.SIMPLIFY
            response = _build_simplify_response(missing, explanation)
        else:
            action = SocraticAction.HINT
            response = _build_hint_response(covered, missing, hint)
    else:  # incorrect
        if attempt_count >= 3:
            action = SocraticAction.SIMPLIFY
            response = _build_simplify_response(missing, explanation)
        else:
            action = SocraticAction.RETRY
            response = _build_retry_response(explanation)

    result = SocraticStepResult(
        step_id=step_id,
        student_answer_quality=quality,
        covered_points=covered,
        missing_points=missing,
        action=action,
        response=response,
    )

    return ServiceResult(success=True, result=result)


def complete_socratic(
    socratic_id: str,
    covered_points: list[str],
    weak_points: list[str],
) -> ServiceResult[SocraticCompleteResult]:
    """生成苏格拉底引导完成结果"""
    chain = load_socratic_chain(socratic_id)
    summary = chain.get("final_summary", "") if chain else ""

    if chain is None:
        return ServiceResult(
            success=False,
            errors=[ServiceError(
                type=ServiceErrorType.KNOWLEDGE_NOT_FOUND,
                message=f"未找到苏格拉底引导链：{socratic_id}",
            )],
        )

    result = SocraticCompleteResult(
        socratic_id=socratic_id,
        completed=True,
        covered_points=covered_points,
        remaining_weak_points=weak_points,
        summary=summary,
    )

    return ServiceResult(success=True, result=result)


# ═══════════════════════════════════════════════════════════
# LLM Agent 集成
# ═══════════════════════════════════════════════════════════

def _judge_with_agent(
    llm_client,
    step: dict,
    student_answer: str,
    attempt_count: int,
    socratic_chain: dict | None = None,
) -> ServiceResult[SocraticStepResult] | None:
    """Use SocraticAgent to judge the answer via LLM."""
    import asyncio
    from agents.socratic_agent import SocraticAgent

    step_id = step.get("step", 0)

    agent_ctx = create_agent_context(
        session_id="socratic",
        student_input=student_answer,
        socratic_chain=socratic_chain or {"steps": [step]},
        metadata={
            "step_index": step_id,
            "attempt_count": attempt_count,
        },
    )

    agent = SocraticAgent(llm_client)
    agent_result = _run_async(agent.run(agent_ctx))

    if not agent_result or not agent_result.structured_data:
        return None

    sd = agent_result.structured_data

    # Map string actions to enums
    action_str = sd.get("action", "hint")
    action_map = {
        "advance": SocraticAction.ADVANCE,
        "hint": SocraticAction.HINT,
        "retry": SocraticAction.RETRY,
        "simplify": SocraticAction.SIMPLIFY,
        "complete": SocraticAction.COMPLETE,
    }
    action = action_map.get(action_str, SocraticAction.HINT)

    quality_str = sd.get("quality", "partial")
    quality_map = {
        "complete": AnswerQuality.COMPLETE,
        "partial": AnswerQuality.PARTIAL,
        "incorrect": AnswerQuality.INCORRECT,
    }
    quality = quality_map.get(quality_str, AnswerQuality.PARTIAL)

    result = SocraticStepResult(
        step_id=step_id,
        student_answer_quality=quality,
        covered_points=sd.get("covered_points", []),
        missing_points=sd.get("missing_points", []),
        action=action,
        response=sd.get("response", ""),
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

def judge_answer_legacy(
    step: dict,
    student_answer: str,
    attempt_count: int,
) -> dict:
    """
    [deprecated] 旧 dict 接口，内部委托给 judge_answer()。

    Streamlit 页面在 Phase 3 迁移前继续使用此函数。
    """
    sr = judge_answer(step, student_answer, attempt_count)
    if sr.success and sr.result:
        return sr.result.model_dump()
    return {
        "step_id": step.get("step", 0),
        "student_answer_quality": "incorrect",
        "covered_points": [],
        "missing_points": [],
        "action": "retry",
        "response": sr.errors[0].message if sr.errors else "判断出错",
    }


def complete_socratic_legacy(
    socratic_id: str,
    covered_points: list[str],
    weak_points: list[str],
) -> dict:
    """
    [deprecated] 旧 dict 接口，内部委托给 complete_socratic()。
    """
    sr = complete_socratic(socratic_id, covered_points, weak_points)
    if sr.success and sr.result:
        return sr.result.model_dump()
    return {
        "socratic_id": socratic_id,
        "completed": False,
        "covered_points": covered_points,
        "remaining_weak_points": weak_points,
        "summary": "",
    }
