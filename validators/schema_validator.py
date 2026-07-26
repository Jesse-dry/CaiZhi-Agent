"""
Schema 校验器 — 纯确定性检查，不依赖 LLM。

检查项：
  - Pydantic 模型校验（字段类型、必填、约束）
  - ID 格式规范
  - 枚举值有效性
  - 分数/范围合理性
  - 苏格拉底分支指针存在性（step_id 不能指向不存在的节点）
  - 选项数量（QA 题目应为 4 个选项）
"""

from __future__ import annotations

import re
from typing import Any

from schemas.dataset_item import (
    QADatasetItem,
    StudentAnswerSample,
    SocraticDatasetItem,
    FeynmanTask,
    FeynmanStudentResponse,
    DatasetStatus,
    QuestionType,
    AnswerLevel,
)


# ID 格式正则
QA_ID_PATTERN = re.compile(r"^Q_AUTO_\d{4}$")
SA_ID_PATTERN = re.compile(r"^SA_AUTO_\d{4}$")
SOCRATIC_ID_PATTERN = re.compile(r"^S_AUTO_\d{4}$")
FEYNMAN_TASK_ID_PATTERN = re.compile(r"^F_AUTO_\d{4}$")
FEYNMAN_RESPONSE_ID_PATTERN = re.compile(r"^FR_AUTO_\d{4}$")


def validate_qa_item(data: dict) -> tuple[bool, list[str]]:
    """
    校验 QA 题目。

    返回 (is_valid, errors)
    """
    errors: list[str] = []

    # 1. Pydantic 校验
    try:
        item = QADatasetItem(**data)
    except Exception as e:
        return False, [f"Pydantic validation failed: {e}"]

    # 2. ID 格式
    if not QA_ID_PATTERN.match(item.id):
        errors.append(f"Invalid QA ID format: {item.id}, expected Q_AUTO_XXXX")

    # 3. 选项数量（应为 4）
    if len(item.options) != 4:
        errors.append(f"Expected 4 options, got {len(item.options)}")

    # 4. answer 必须是 options 中的一个 key
    if item.answer not in item.options:
        errors.append(f"Answer '{item.answer}' not in options keys: {list(item.options.keys())}")

    # 5. diagnosis 的 key 应与错误选项一致（不能诊断正确答案）
    wrong_options = [k for k in item.options if k != item.answer]
    for key in item.diagnosis:
        if key == item.answer:
            errors.append(f"Diagnosis contains correct answer key: {key}")
        if key not in item.options:
            errors.append(f"Diagnosis key '{key}' not in options")

    # 6. reference_answer 不应为空
    if not item.reference_answer.strip():
        errors.append("reference_answer is empty")

    # 7. key_points 不应为空
    if not item.key_points:
        errors.append("key_points is empty")

    # 8. difficulty 范围
    if item.difficulty not in (1, 2, 3):
        errors.append(f"Invalid difficulty: {item.difficulty}")

    # 9. question_type 必须是有效枚举值
    try:
        QuestionType(item.question_type)
    except ValueError:
        errors.append(f"Invalid question_type: {item.question_type}")

    return len(errors) == 0, errors


def validate_student_answer(data: dict) -> tuple[bool, list[str]]:
    """校验分级学生答案"""
    errors: list[str] = []

    try:
        item = StudentAnswerSample(**data)
    except Exception as e:
        return False, [f"Pydantic validation failed: {e}"]

    if not SA_ID_PATTERN.match(item.id):
        errors.append(f"Invalid SA ID format: {item.id}, expected SA_AUTO_XXXX")

    if not item.question_id:
        errors.append("question_id is empty")

    if not item.student_answer.strip():
        errors.append("student_answer is empty")

    try:
        AnswerLevel(item.answer_level)
    except ValueError:
        errors.append(f"Invalid answer_level: {item.answer_level}")

    # expected_score_range 应包含 2 个整数
    if item.expected_score_range and len(item.expected_score_range) != 2:
        errors.append(f"expected_score_range should have exactly 2 elements, got {len(item.expected_score_range)}")

    return len(errors) == 0, errors


def validate_socratic_item(data: dict) -> tuple[bool, list[str]]:
    """校验苏格拉底引导链"""
    errors: list[str] = []

    try:
        item = SocraticDatasetItem(**data)
    except Exception as e:
        return False, [f"Pydantic validation failed: {e}"]

    if not SOCRATIC_ID_PATTERN.match(item.id):
        errors.append(f"Invalid Socratic ID format: {item.id}, expected S_AUTO_XXXX")

    if not item.steps:
        errors.append("steps is empty — socratic chain must have at least one step")

    # 收集所有 step_id
    all_step_ids = {s.step_id for s in item.steps}

    # 检查是否有入口节点
    entry_steps = [s for s in item.steps if s.is_entry]
    if not entry_steps:
        errors.append("No entry step found — at least one step must have is_entry=True")

    # 检查分支指针有效性
    for step in item.steps:
        for pointer_name, pointer_value in [
            ("next_if_correct", step.next_if_correct),
            ("next_if_partial", step.next_if_partial),
            ("next_if_wrong", step.next_if_wrong),
        ]:
            if pointer_value is not None and pointer_value not in all_step_ids:
                errors.append(
                    f"Step '{step.step_id}' {pointer_name}='{pointer_value}' "
                    f"points to non-existent step"
                )

    # 检查能否从入口节点到达所有节点
    reachable = _find_reachable(entry_steps[0].step_id if entry_steps else "", item.steps)
    for step in item.steps:
        if step.step_id not in reachable:
            errors.append(f"Step '{step.step_id}' is not reachable from entry node")

    # completion_condition 检查
    if not item.completion_condition.required_concepts:
        errors.append("completion_condition.required_concepts is empty")

    return len(errors) == 0, errors


def _find_reachable(start_id: str, steps: list) -> set[str]:
    """BFS 找出从 start_id 可达的所有节点"""
    step_map = {s.step_id: s for s in steps}
    reachable: set[str] = set()
    queue = [start_id]

    while queue:
        current = queue.pop(0)
        if current in reachable or current not in step_map:
            continue
        reachable.add(current)
        step = step_map[current]
        for next_id in [step.next_if_correct, step.next_if_partial, step.next_if_wrong]:
            if next_id and next_id not in reachable:
                queue.append(next_id)

    return reachable


def validate_feynman_task(data: dict) -> tuple[bool, list[str]]:
    """校验费曼任务"""
    errors: list[str] = []

    try:
        item = FeynmanTask(**data)
    except Exception as e:
        return False, [f"Pydantic validation failed: {e}"]

    if not FEYNMAN_TASK_ID_PATTERN.match(item.id):
        errors.append(f"Invalid Feynman Task ID format: {item.id}, expected F_AUTO_XXXX")

    if not item.prompt.strip():
        errors.append("prompt is empty")

    if not item.mandatory_points:
        errors.append("mandatory_points is empty")

    if not item.checklist:
        errors.append("checklist is empty")

    # rubric 总分应为 100
    rubric_total = (
        item.rubric.concept_accuracy
        + item.rubric.causal_chain_completeness
        + item.rubric.terminology
        + item.rubric.application_transfer
        + item.rubric.clarity
    )
    if rubric_total != 100:
        errors.append(f"Rubric weights sum to {rubric_total}, expected 100")

    return len(errors) == 0, errors


def validate_feynman_response(data: dict) -> tuple[bool, list[str]]:
    """校验费曼学生回答"""
    errors: list[str] = []

    try:
        item = FeynmanStudentResponse(**data)
    except Exception as e:
        return False, [f"Pydantic validation failed: {e}"]

    if not FEYNMAN_RESPONSE_ID_PATTERN.match(item.id):
        errors.append(f"Invalid Feynman Response ID format: {item.id}, expected FR_AUTO_XXXX")

    if not item.feynman_id:
        errors.append("feynman_id is empty")

    if not item.response.strip():
        errors.append("response is empty")

    if item.expected_score_range and len(item.expected_score_range) != 2:
        errors.append(f"expected_score_range should have 2 elements, got {len(item.expected_score_range)}")

    return len(errors) == 0, errors


def validate_item(data: dict, item_type: str) -> tuple[bool, list[str]]:
    """
    统一入口：根据类型分发到对应校验函数。

    参数:
        data: 候选数据 dict
        item_type: "qa" | "student_answer" | "socratic" | "feynman_task" | "feynman_response"

    返回:
        (is_valid, errors)
    """
    validators = {
        "qa": validate_qa_item,
        "student_answer": validate_student_answer,
        "socratic": validate_socratic_item,
        "feynman_task": validate_feynman_task,
        "feynman_response": validate_feynman_response,
    }

    validator = validators.get(item_type)
    if validator is None:
        return False, [f"Unknown item_type: {item_type}"]

    return validator(data)


__all__ = [
    "validate_qa_item",
    "validate_student_answer",
    "validate_socratic_item",
    "validate_feynman_task",
    "validate_feynman_response",
    "validate_item",
]
