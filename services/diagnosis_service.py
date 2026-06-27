from knowledge.misconception_mapper import (
    get_question_by_id,
    diagnose_answer,
    list_questions
)


def get_all_questions():
    """给页面展示题目列表"""
    return list_questions()


def get_question_for_page(question_id: str = "Q001"):
    """
    给 Streamlit 页面用的题目数据。
    只返回前端需要展示的字段。
    """
    question = get_question_by_id(question_id)

    if question is None:
        return None

    return {
        "question_id": question.get("question_id", ""),
        "topic": question.get("topic", ""),
        "question": question.get("question", ""),
        "options": question.get("options", {}),
        "difficulty": question.get("difficulty", "basic")
    }


def submit_answer(question_id: str, selected_option: str):
    """
    接收学生答案，返回诊断结果。
    """
    return diagnose_answer(question_id, selected_option)