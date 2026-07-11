"""
苏格拉底引导 — 请求与结果

POST /api/socratic/judge 的契约定义。
"""

from pydantic import BaseModel, Field
from schemas.common import AnswerQuality, SocraticAction


class JudgeAnswerRequest(BaseModel):
    """单步回答评判请求"""
    session_id: str = Field(..., description="会话 ID")
    socratic_id: str = Field(..., description="苏格拉底引导链 ID，如 S001")
    step_index: int = Field(..., description="当前步骤序号（1-indexed）", ge=1)
    student_answer: str = Field(..., description="学生回答文本", min_length=1)
    attempt_count: int = Field(default=1, description="当前步骤的尝试次数", ge=1)


class SocraticStep(BaseModel):
    """苏格拉底引导链中的一个教学台阶（只读，供前端展示）"""
    step: int = Field(..., description="步骤序号")
    question: str = Field(..., description="引导问题")
    expected_keywords: list[str] = Field(default_factory=list, description="期望关键词")
    hint: str = Field(default="", description="提示文本")
    explanation_if_wrong: str = Field(default="", description="错误时的解释")


class SocraticStepResult(BaseModel):
    """
    单步评判结果。

    services/socratic_service.judge_answer() 的返回值。
    """
    step_id: int = Field(..., description="步骤序号")
    student_answer_quality: AnswerQuality = Field(..., description="回答质量评级")
    covered_points: list[str] = Field(default_factory=list, description="已覆盖的知识点")
    missing_points: list[str] = Field(default_factory=list, description="缺失的知识点")
    action: SocraticAction = Field(..., description="系统动作")
    response: str = Field(default="", description="助教反馈文本")


class SocraticChainInfo(BaseModel):
    """苏格拉底引导链元信息（只读）"""
    socratic_id: str = Field(..., description="引导链 ID")
    title: str = Field(default="", description="引导链标题")
    total_steps: int = Field(..., description="总步骤数")
    steps: list[SocraticStep] = Field(default_factory=list, description="所有步骤")


class SocraticCompleteResult(BaseModel):
    """
    苏格拉底引导完成结果。

    services/socratic_service.complete_socratic() 的返回值。
    """
    socratic_id: str = Field(..., description="引导链 ID")
    completed: bool = Field(default=True, description="是否完成")
    covered_points: list[str] = Field(default_factory=list, description="最终覆盖的知识点")
    remaining_weak_points: list[str] = Field(default_factory=list, description="仍薄弱的知识点")
    summary: str = Field(default="", description="核心结论总结")


class SocraticState(BaseModel):
    """苏格拉底引导的运行时状态（前端轮询/SSE 用）"""
    socratic_id: str = Field(..., description="引导链 ID")
    current_step: int = Field(default=1, description="当前步骤")
    total_steps: int = Field(..., description="总步骤数")
    attempt_count: int = Field(default=0, description="当前步骤尝试次数")
    all_covered: list[str] = Field(default_factory=list, description="已覆盖的知识点汇总")
    all_weak: list[str] = Field(default_factory=list, description="薄弱知识点汇总")
    completed: bool = Field(default=False, description="是否全部完成")
    history: list[dict] = Field(default_factory=list, description="对话历史")
