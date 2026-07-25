"""
材智 Agent 自动评测基线。

用法:
    python -m evaluation              # 终端表格输出全部指标
    python -m evaluation --json       # JSON 输出
    python -m evaluation --metric X   # 单指标输出
"""

from evaluation.evaluator import Evaluator
from evaluation.test_cases import (
    load_qa_cases,
    load_question_tests,
    load_feynman_tests,
    load_socratic_tests,
    load_learning_path_scenarios,
)

__all__ = [
    "Evaluator",
    "load_qa_cases",
    "load_question_tests",
    "load_feynman_tests",
    "load_socratic_tests",
    "load_learning_path_scenarios",
]
