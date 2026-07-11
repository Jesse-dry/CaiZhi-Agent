"""
学习路径推荐 — 请求与结果

POST /api/learning-path/generate 的契约定义。
"""

from pydantic import BaseModel, Field
from schemas.common import MasteryLevel


class KnowledgeUnit(BaseModel):
    """知识单元定义"""
    knowledge_id: str = Field(..., description="知识单元 ID，如 K001")
    title: str = Field(..., description="知识单元标题")
    description: str = Field(default="", description="简要描述")
    prerequisites: list[str] = Field(default_factory=list, description="先修知识单元 ID 列表")
    keywords: list[str] = Field(default_factory=list, description="关键词（用于薄弱点匹配）")


class RecommendedStep(BaseModel):
    """单个推荐学习步骤"""
    order: int = Field(..., description="推荐顺序（1-indexed）", ge=1)
    knowledge_id: str = Field(..., description="知识单元 ID")
    title: str = Field(default="", description="知识单元标题")
    reason: str = Field(default="", description="推荐原因")
    source: str = Field(default="", description="薄弱点来源：diagnosis / socratic / feynman")


class GeneratePathRequest(BaseModel):
    """学习路径推荐请求"""
    session_id: str = Field(..., description="会话 ID")
    diagnosis_result: dict | None = Field(default=None, description="错题诊断结果（过渡期接受 dict）")
    socratic_result: dict | None = Field(default=None, description="苏格拉底引导结果（过渡期接受 dict）")
    feynman_result: dict | None = Field(default=None, description="费曼评价结果（过渡期接受 dict）")


class WeakPointDetail(BaseModel):
    """薄弱点详细信息"""
    point: str = Field(..., description="薄弱点描述")
    source: str = Field(..., description="来源：diagnosis / socratic / feynman")
    mapped_knowledge_id: str = Field(default="", description="映射到的知识单元 ID")


class LearningPathResult(BaseModel):
    """
    学习路径推荐完整结果。

    services/recommendation_service.generate_learning_path() 的返回值。
    """
    current_level: MasteryLevel = Field(..., description="当前掌握程度评级")
    weak_points: list[WeakPointDetail] = Field(default_factory=list, description="薄弱点列表（含来源追踪）")
    recommended_steps: list[RecommendedStep] = Field(default_factory=list, description="推荐学习步骤（先修关系已排序）")

    # ── 元信息 ──
    total_weak_points: int = Field(default=0, description="薄弱点总数")
    total_recommended_steps: int = Field(default=0, description="推荐步骤总数")
    generated_at: str = Field(default="", description="生成时间 ISO 时间戳")


# ═══════════════════════════════════════════════════════════
# V1 过渡期兼容类型（后续移除）
# ═══════════════════════════════════════════════════════════

class LearningPathResultV1(BaseModel):
    """V1 兼容格式 — generate_learning_path() 当前返回的 dict 结构"""
    current_level: str = Field(default="需要加强", description="当前掌握程度")
    weak_points: list[str] = Field(default_factory=list, description="薄弱知识点列表（纯字符串）")
    recommended_steps: list[dict] = Field(default_factory=list, description="推荐步骤（dict 格式）")
