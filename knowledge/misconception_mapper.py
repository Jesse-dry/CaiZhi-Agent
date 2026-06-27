import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = BASE_DIR / "data" / "questions.json"


def load_questions():
    """读取 questions.json"""
    with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def list_questions():
    """返回所有题目"""
    return load_questions()


def get_question_by_id(question_id: str):
    """根据 question_id 找到某一道题"""
    questions = load_questions()

    for question in questions:
        if question.get("question_id") == question_id:
            return question

    return None


def diagnose_answer(question_id: str, selected_option: str):
    """
    诊断学生选择。
    输入：题目 ID + 学生选项
    输出：正误、误区、缺失知识点、补救路径
    """
    question = get_question_by_id(question_id)

    if question is None:
        return {
            "success": False,
            "message": f"未找到题目：{question_id}"
        }

    selected_option = selected_option.strip().upper()
    correct_answer = question.get("answer", "").strip().upper()
    is_correct = selected_option == correct_answer

    base_result = {
        "success": True,
        "question_id": question_id,
        "question": question.get("question", ""),
        "selected_option": selected_option,
        "selected_text": question.get("options", {}).get(selected_option, ""),
        "correct_answer": correct_answer,
        "correct_text": question.get("options", {}).get(correct_answer, ""),
        "is_correct": is_correct,
        "answer_explanation": question.get("answer_explanation", ""),
        "knowledge_points": question.get("knowledge_points", []),
        "next_chain_id": question.get("next_chain_id", ""),
        "next_socratic_id": question.get("next_socratic_id", "")
    }

    if is_correct:
        base_result.update({
            "diagnosis_type": "correct",
            "message": "回答正确。你已经掌握了这个知识点的核心因果链。",
            "misconception": "",
            "error_reason": "",
            "missing_points": [],
            "feedback": "可以继续进入费曼解释环节，尝试用自己的话讲清楚原因。",
            "remedial_path": question.get("knowledge_points", [])
        })
        return base_result

    diagnosis = question.get("diagnosis", {}).get(selected_option, {})

    base_result.update({
        "diagnosis_type": "wrong",
        "message": "回答错误。系统已根据你的错误选项定位到对应误区。",
        "misconception": diagnosis.get("misconception", "暂未配置该选项的误区。"),
        "error_reason": diagnosis.get("error_reason", ""),
        "missing_points": diagnosis.get("missing_points", []),
        "feedback": diagnosis.get("feedback", ""),
        "remedial_path": diagnosis.get("remedial_path", [])
    })

    return base_result