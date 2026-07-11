"""
错题诊断服务层。

输入：question_id + 学生选项
输出：统一 diagnosis_result dict，包含误区定位、缺失知识点、推荐路径。
"""

from knowledge.misconception_mapper import get_question_by_id, list_questions


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


def submit_answer(question_id: str, selected_option: str) -> dict:
    """
    诊断学生答案，返回统一的 diagnosis_result。

    返回结构:
        {
            "question_id": "Q001",
            "selected_option": "A",
            "is_correct": bool,
            "misconception_id": "M_Q001_A",     # 新增
            "misconception": "...",
            "misconception_label": "...",
            "error_reason": "...",
            "missing_concepts": [...],           # 统一命名
            "feedback": "...",
            "remedial_path": [...],
            "recommended_chain_id": "C001",     # 统一命名
            "recommended_socratic_id": "S001",  # 统一命名
            "answer_explanation": "...",
            "knowledge_points": [...],
        }
    """
    from knowledge.misconception_mapper import diagnose_answer

    raw = diagnose_answer(question_id, selected_option)

    if not raw.get("success"):
        return {
            "question_id": question_id,
            "selected_option": selected_option,
            "is_correct": False,
            "misconception_id": "",
            "misconception": "",
            "misconception_label": "",
            "error_reason": "",
            "missing_concepts": [],
            "feedback": raw.get("message", "诊断失败"),
            "remedial_path": [],
            "recommended_chain_id": "",
            "recommended_socratic_id": "",
            "answer_explanation": "",
            "knowledge_points": [],
        }

    # 误区 ID：稳定可追溯
    misconception_id = (
        f"M_{question_id}_{selected_option}" if not raw.get("is_correct") else ""
    )

    return {
        "question_id": raw.get("question_id", question_id),
        "selected_option": raw.get("selected_option", selected_option),
        "is_correct": raw.get("is_correct", False),
        "misconception_id": misconception_id,
        "misconception": raw.get("misconception", ""),
        "misconception_label": raw.get("misconception", ""),  # 展示用
        "error_reason": raw.get("error_reason", ""),
        "missing_concepts": raw.get("missing_points", []),
        "feedback": raw.get("feedback", ""),
        "remedial_path": raw.get("remedial_path", []),
        "recommended_chain_id": raw.get("next_chain_id", ""),
        "recommended_socratic_id": raw.get("next_socratic_id", ""),
        "answer_explanation": raw.get("answer_explanation", ""),
        "knowledge_points": raw.get("knowledge_points", []),
    }
