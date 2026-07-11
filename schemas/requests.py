"""
[已废弃] 请求数据结构 — 请使用按业务域拆分的模块

旧路径 → 新路径：
    AnswerQuestionRequest    → schemas.qa.QARequest
    SubmitAnswerRequest      → schemas.diagnosis.DiagnosisRequest
    JudgeAnswerRequest       → schemas.socratic.JudgeAnswerRequest
    EvaluateExplanationRequest → schemas.feynman.EvaluateRequest
    GenerateLearningPathRequest → schemas.recommendation.GeneratePathRequest

保留此文件仅为向后兼容，新代码请直接从 domain 模块导入。
"""

# 向后兼容重导出
from schemas.qa import QARequest as AnswerQuestionRequest
from schemas.diagnosis import DiagnosisRequest as SubmitAnswerRequest
from schemas.socratic import JudgeAnswerRequest
from schemas.feynman import EvaluateRequest as EvaluateExplanationRequest
from schemas.recommendation import GeneratePathRequest as GenerateLearningPathRequest

__all__ = [
    "AnswerQuestionRequest",
    "SubmitAnswerRequest",
    "JudgeAnswerRequest",
    "EvaluateExplanationRequest",
    "GenerateLearningPathRequest",
]
