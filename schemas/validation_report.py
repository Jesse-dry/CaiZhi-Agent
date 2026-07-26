"""
校验报告 — 自动校验的输出模型。

包含 6 维度质量评分和发布门禁规则。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
# 质量评分（6 维度）
# ═══════════════════════════════════════════════════════════

class QualityScore(BaseModel):
    """
    质量评分 — 6 个维度，满分 100。

    发布门禁：
      - 存在事实错误 / 无有效教材证据 / 图谱关系冲突 → 直接拒绝
      - total < 70 → reject
      - 70 ≤ total < 85 → needs_careful_review（人工重点审核）
      - total ≥ 85 → normal_review（进入普通审核队列）

    注意：即使 total ≥ 85，仍不建议第一阶段完全无人审核。
    """
    evidence_support: float = Field(
        default=0.0, ge=0.0, le=30.0,
        description="教材证据支持度 — source_refs 能否支撑核心陈述",
    )
    graph_consistency: float = Field(
        default=0.0, ge=0.0, le=20.0,
        description="知识图谱一致性 — graph_path 节点与边关系是否正确",
    )
    answer_clarity: float = Field(
        default=0.0, ge=0.0, le=15.0,
        description="答案唯一性或任务清晰度 — 正确答案是否唯一、题目是否有歧义",
    )
    teaching_value: float = Field(
        default=0.0, ge=0.0, le=15.0,
        description="教学与诊断价值 — 是否有助于学习或发现误区",
    )
    distinctiveness: float = Field(
        default=0.0, ge=0.0, le=10.0,
        description="与现有数据的差异性 — 是否与已有题目/任务高度重复",
    )
    terminology_accuracy: float = Field(
        default=0.0, ge=0.0, le=10.0,
        description="语言与术语规范 — 术语是否符合 terms.csv 标准",
    )

    @property
    def total(self) -> float:
        """总分 0-100"""
        return round(
            self.evidence_support
            + self.graph_consistency
            + self.answer_clarity
            + self.teaching_value
            + self.distinctiveness
            + self.terminology_accuracy,
            1,
        )

    @property
    def verdict(self) -> str:
        """发布门禁判定"""
        if self.total < 70:
            return "reject"
        if self.total < 85:
            return "needs_careful_review"
        return "normal_review"

    @property
    def is_fatal(self) -> bool:
        """是否存在致命缺陷（无证据 / 图谱冲突）"""
        return self.evidence_support < 5.0 or self.graph_consistency < 5.0


# ═══════════════════════════════════════════════════════════
# 校验报告
# ═══════════════════════════════════════════════════════════

class ValidationReport(BaseModel):
    """
    单条候选数据的校验报告。

    包含 5 项确定性检查（不依赖 LLM） + 质量评分。
    """
    item_id: str = Field(..., description="被校验的数据条目 ID")
    item_type: str = Field(default="qa", description="条目类型：qa / socratic / feynman / student_answer")

    # ── 5 项确定性检查 ──
    schema_valid: bool = Field(default=False, description="Pydantic schema 校验通过")
    schema_errors: list[str] = Field(default_factory=list, description="Schema 校验错误详情")

    evidence_valid: bool = Field(default=False, description="source_refs 全部在 ChromaDB 中存在")
    evidence_errors: list[str] = Field(default_factory=list, description="证据校验错误详情")
    missing_chunk_ids: list[str] = Field(default_factory=list, description="不存在的 chunk_id 列表")

    graph_consistent: bool = Field(default=False, description="graph_path 与 KG 边关系一致")
    graph_errors: list[str] = Field(default_factory=list, description="图谱校验错误详情")
    invalid_nodes: list[str] = Field(default_factory=list, description="不存在的 KG 节点 ID")

    terminology_valid: bool = Field(default=False, description="所有材料学术语在 terms.csv 中")
    terminology_errors: list[str] = Field(default_factory=list, description="术语校验错误详情")
    unknown_terms: list[str] = Field(default_factory=list, description="不在 terms.csv 中的术语")

    duplicate_detected: bool = Field(default=False, description="检测到疑似重复")
    duplicate_similarity: float = Field(default=0.0, ge=0.0, le=1.0, description="最高相似度")
    similar_item_ids: list[str] = Field(default_factory=list, description="相似题目 ID 列表")

    # ── 质量评分 ──
    quality_score: QualityScore | None = Field(default=None, description="6 维度质量评分")

    # ── 汇总 ──
    errors: list[str] = Field(default_factory=list, description="所有错误信息汇总")
    warnings: list[str] = Field(default_factory=list, description="所有警告信息汇总")

    @property
    def all_checks_passed(self) -> bool:
        """所有确定性检查是否全部通过"""
        return (
            self.schema_valid
            and self.evidence_valid
            and self.graph_consistent
            and self.terminology_valid
            and not self.duplicate_detected
        )

    @property
    def is_publishable(self) -> bool:
        """是否满足发布条件（无致命错误 + 质量分达标）"""
        if not self.all_checks_passed:
            return False
        if self.quality_score is None:
            return False
        return not self.quality_score.is_fatal and self.quality_score.verdict != "reject"


class BatchValidationReport(BaseModel):
    """批量校验报告"""
    batch_id: str = Field(..., description="批次 ID")
    total_items: int = Field(default=0, description="校验总数")
    passed: int = Field(default=0, description="全部通过数")
    failed: int = Field(default=0, description="存在失败项数")
    publishable: int = Field(default=0, description="可发布数")
    reports: list[ValidationReport] = Field(default_factory=list, description="逐条报告")

    @property
    def pass_rate(self) -> float:
        """通过率"""
        if self.total_items == 0:
            return 0.0
        return round(self.passed / self.total_items * 100, 1)

    @property
    def publishable_rate(self) -> float:
        """可发布率"""
        if self.total_items == 0:
            return 0.0
        return round(self.publishable / self.total_items * 100, 1)
