"""
[已废弃] 结果数据结构 — 请使用按业务域拆分的模块

旧路径 → 新路径：
    QAResult                → schemas.qa.QAResult
    DiagnosisResult         → schemas.diagnosis.DiagnosisResult
    SocraticStepResult      → schemas.socratic.SocraticStepResult
    SocraticCompleteResult  → schemas.socratic.SocraticCompleteResult
    FeynmanResult           → schemas.feynman.FeynmanResult
    DimensionScores         → schemas.feynman.DimensionScores
    LearningPathResult      → schemas.recommendation.LearningPathResult
    RecommendedStep         → schemas.recommendation.RecommendedStep

保留此文件仅为向后兼容，新代码请直接从 domain 模块导入。
"""

from schemas.qa import QAResult
from schemas.diagnosis import DiagnosisResult
from schemas.socratic import SocraticStepResult, SocraticCompleteResult
from schemas.feynman import FeynmanResult, DimensionScores
from schemas.recommendation import RecommendedStep, LearningPathResult

__all__ = [
    "QAResult",
    "DiagnosisResult",
    "SocraticStepResult",
    "SocraticCompleteResult",
    "FeynmanResult",
    "DimensionScores",
    "LearningPathResult",
    "RecommendedStep",
]
