"""
错题诊断 — 请求与结果

POST /api/diagnosis/submit 的契约定义。
"""

from pydantic import BaseModel, Field
from schemas.common import Difficulty


class DiagnosisRequest(BaseModel):
    """错题诊断请求"""
    session_id: str = Field(..., description="会话 ID")
    question_id: str = Field(..., description="题目 ID，如 Q001")
    selected_option: str = Field(..., description="学生选择的选项", min_length=1, max_length=1)


class MisconceptionDetail(BaseModel):
    """单个误区的详细信息"""
    misconception_id: str = Field(..., description="误区唯一 ID，如 M_Q001_A")
    misconception: str = Field(..., description="误区名称/简述")
    error_reason: str = Field(default="", description="错误原因分析")
    missing_concepts: list[str] = Field(default_factory=list, description="缺失的知识点")
    feedback: str = Field(default="", description="针对性反馈文本")
    remedial_path: list[str] = Field(default_factory=list, description="补救学习路径（知识点列表）")


class DiagnosisResult(BaseModel):
    """
    错题诊断完整结果。

    services/diagnosis_service.submit_answer() 的返回值。
    """
    # ── 基础信息 ──
    question_id: str = Field(..., description="题目 ID")
    selected_option: str = Field(..., description="学生选择的选项")
    is_correct: bool = Field(..., description="是否回答正确")

    # ── 误区诊断 ──
    misconception_id: str = Field(default="", description="误区唯一 ID，正确时为空")
    misconception: str = Field(default="", description="误区简述")
    misconception_label: str = Field(default="", description="误区展示标签")
    error_reason: str = Field(default="", description="错误原因")
    missing_concepts: list[str] = Field(default_factory=list, description="缺失的知识点列表")

    # ── 反馈 ──
    feedback: str = Field(default="", description="针对性反馈")
    remedial_path: list[str] = Field(default_factory=list, description="补救学习步骤")

    # ── 推荐下一步 ──
    recommended_chain_id: str = Field(default="", description="推荐复习的因果链 ID")
    recommended_socratic_id: str = Field(default="", description="推荐的苏格拉底引导链 ID")

    # ── 题目元信息 ──
    answer_explanation: str = Field(default="", description="正确答案解释")
    knowledge_points: list[str] = Field(default_factory=list, description="题目考察的知识点")
    difficulty: str = Field(default="basic", description="难度：basic / intermediate / advanced")
