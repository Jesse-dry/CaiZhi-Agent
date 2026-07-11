"""
费曼学习法评价 — 请求与结果

POST /api/feynman/evaluate 的契约定义。
"""

from pydantic import BaseModel, Field, model_validator


class EvaluateRequest(BaseModel):
    """费曼评价请求"""
    session_id: str = Field(..., description="会话 ID")
    explanation: str = Field(..., description="学生的费曼解释文本", min_length=1, max_length=5000)
    feynman_id: str = Field(default="F001", description="评价标准 ID")


class DimensionScores(BaseModel):
    """
    费曼五维度评分。

    每个维度有独立满分值，总分 = 五维度之和（满分 78）。
    """
    concept_accuracy: int = Field(default=0, description="概念准确性", ge=0, le=18)
    causal_completeness: int = Field(default=0, description="因果链完整性", ge=0, le=20)
    term_accuracy: int = Field(default=0, description="术语规范性", ge=0, le=14)
    clarity: int = Field(default=0, description="表达清晰度", ge=0, le=16)
    misconception_control: int = Field(default=10, description="误区控制（V1 默认满分）", ge=0, le=10)

    @property
    def total(self) -> int:
        return (
            self.concept_accuracy
            + self.causal_completeness
            + self.term_accuracy
            + self.clarity
            + self.misconception_control
        )

    @property
    def max_total(self) -> int:
        return 18 + 20 + 14 + 16 + 10  # 78

    @property
    def percentage(self) -> float:
        return round(self.total / self.max_total * 100, 1)


class ChecklistItem(BaseModel):
    """评分清单条目（只读，供前端展示）"""
    point: str = Field(..., description="评分点描述")
    keywords: list[str] = Field(default_factory=list, description="关键词")
    max_score: int = Field(default=0, description="该点满分")


class FeynmanRubric(BaseModel):
    """费曼评价标准（只读）"""
    feynman_id: str = Field(..., description="评价标准 ID")
    topic: str = Field(default="", description="主题")
    prompt: str = Field(default="", description="费曼挑战描述")
    checklist: list[ChecklistItem] = Field(default_factory=list, description="评分清单")
    excellent_example: str = Field(default="", description="优秀范例文本")


class FeynmanResult(BaseModel):
    """
    费曼评价完整结果。

    services/feynman_service.evaluate() 的返回值。
    """
    feynman_id: str = Field(..., description="评价标准 ID")
    total_score: int = Field(..., description="总分（满分 78）", ge=0, le=78)
    dimension_scores: DimensionScores = Field(default_factory=DimensionScores, description="五维度评分明细")
    covered_points: list[str] = Field(default_factory=list, description="讲清楚的部分")
    missing_points: list[str] = Field(default_factory=list, description="缺失的部分")
    incorrect_points: list[str] = Field(default_factory=list, description="表述有误的部分（V2 LLM 接入后启用）")
    next_question: str = Field(default="", description="建议下一步思考的问题")
