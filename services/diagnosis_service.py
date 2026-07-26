"""
错题诊断服务层。

输入：question_id + 学生选项
输出：ServiceResult[DiagnosisResult]，包含误区定位、缺失知识点、推荐路径。

V2：返回类型化的 Pydantic model，wrapper 用 ServiceResult 统一错误处理。
向后兼容：旧的 dict 接口保留为 submit_answer_legacy()。
"""

from knowledge.misconception_mapper import get_question_by_id, list_questions
from schemas.diagnosis import DiagnosisResult
from schemas.common import ServiceResult, ServiceError, ServiceErrorType


def get_all_questions() -> list[dict]:
    """给页面展示题目列表"""
    return list_questions()


def get_question_for_page(question_id: str) -> dict | None:
    """只返回前端需要展示的字段"""
    question = get_question_by_id(question_id)
    if question is None:
        return None

    return {
        "question_id": question.get("question_id", ""),
        "topic": question.get("topic", ""),
        "question": question.get("question", ""),
        "options": question.get("options", {}),
        "difficulty": question.get("difficulty", "basic"),
    }


# ═══════════════════════════════════════════════════════════
# 新版：返回 ServiceResult[DiagnosisResult]
# ═══════════════════════════════════════════════════════════

def submit_answer(question_id: str, selected_option: str) -> ServiceResult[DiagnosisResult]:
    """
    诊断学生答案，返回 ServiceResult[DiagnosisResult]。

    V2：使用类型化的 DiagnosisResult + ServiceResult wrapper。
    错误路径通过 ServiceResult.errors 明确传递，不再返回空 dict。
    """
    from knowledge.misconception_mapper import diagnose_answer

    raw = diagnose_answer(question_id, selected_option)

    if not raw.get("success"):
        return ServiceResult(
            success=False,
            errors=[ServiceError(
                type=ServiceErrorType.KNOWLEDGE_NOT_FOUND,
                message=raw.get("message", "诊断失败"),
            )],
        )

    # 误区 ID：稳定可追溯
    is_correct = raw.get("is_correct", False)
    misconception_id = (
        f"M_{question_id}_{selected_option}" if not is_correct else ""
    )

    result = DiagnosisResult(
        question_id=raw.get("question_id", question_id),
        selected_option=raw.get("selected_option", selected_option),
        is_correct=is_correct,
        misconception_id=misconception_id,
        misconception=raw.get("misconception", ""),
        misconception_label=raw.get("misconception", ""),
        error_reason=raw.get("error_reason", ""),
        missing_concepts=raw.get("missing_points", []),
        feedback=raw.get("feedback", ""),
        remedial_path=raw.get("remedial_path", []),
        recommended_chain_id=raw.get("next_chain_id", ""),
        recommended_socratic_id=raw.get("next_socratic_id", ""),
        answer_explanation=raw.get("answer_explanation", ""),
        knowledge_points=raw.get("knowledge_points", []),
    )

    return ServiceResult(success=True, result=result)


# ═══════════════════════════════════════════════════════════
# 向后兼容 wrapper — 返回 dict（Streamlit 页面过渡期使用）
# ═══════════════════════════════════════════════════════════

def submit_answer_legacy(question_id: str, selected_option: str) -> dict:
    """
    [deprecated] 旧 dict 接口，内部委托给 submit_answer()。

    Streamlit 页面在 Phase 3 迁移前继续使用此函数。
    新代码请直接调用 submit_answer() 获取 ServiceResult。
    """
    sr = submit_answer(question_id, selected_option)
    if sr.success and sr.result:
        return sr.result.model_dump()
    # 错误路径：返回兼容的空 dict 结构
    return {
        "question_id": question_id,
        "selected_option": selected_option,
        "is_correct": False,
        "misconception_id": "",
        "misconception": "",
        "misconception_label": "",
        "error_reason": "",
        "missing_concepts": [],
        "feedback": sr.errors[0].message if sr.errors else "诊断失败",
        "remedial_path": [],
        "recommended_chain_id": "",
        "recommended_socratic_id": "",
        "answer_explanation": "",
        "knowledge_points": [],
    }
