"""
数据集审核 — 人工审核动作的记录模型。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ReviewAction(StrEnum):
    """审核动作"""
    APPROVE = "approve"          # 批准发布
    REJECT = "reject"            # 拒绝（保留在 rejected/ 用于去重）
    EDIT = "edit"                # 编辑后重新提交
    FLAG = "flag"                # 标记需要讨论
    SKIP = "skip"                # 跳过（暂不处理）
    BATCH_APPROVE = "batch_approve"    # 批量批准
    BATCH_REJECT = "batch_reject"      # 批量拒绝


class ReviewRecord(BaseModel):
    """单条审核记录"""
    review_id: str = Field(..., description="审核记录唯一 ID")
    item_id: str = Field(..., description="被审核的数据条目 ID")
    item_type: str = Field(default="qa", description="条目类型")
    action: ReviewAction = Field(..., description="审核动作")
    reviewer: str = Field(default="human", description="审核人标识")
    reason: str = Field(default="", description="审核原因/备注")
    edited_fields: dict | None = Field(default=None, description="编辑的字段（action=edit 时填写）")
    reviewed_at: str = Field(..., description="审核时间 ISO 8601")


class PublishRequest(BaseModel):
    """发布请求"""
    item_ids: list[str] = Field(..., description="要发布的数据条目 ID 列表", min_length=1)
    item_type: str = Field(default="qa", description="条目类型")
    dataset_version: str = Field(..., description="目标数据集版本，如 2026.08.1")
    publisher: str = Field(default="", description="发布人标识")
    publish_notes: str = Field(default="", description="发布说明")


class DatasetVersion(BaseModel):
    """数据集版本信息"""
    version: str = Field(..., description="版本号，如 2026.08.1")
    item_type: str = Field(..., description="条目类型")
    item_count: int = Field(default=0, description="条目总数")
    published_at: str = Field(default="", description="发布时间")
    published_by: str = Field(default="", description="发布人")
    previous_version: str | None = Field(default=None, description="上一版本号")
    changelog: str = Field(default="", description="变更说明")
    file_path: str = Field(default="", description="正式数据文件路径")


class ReviewStats(BaseModel):
    """审核统计面板数据"""
    total_candidates: int = Field(default=0, description="候选总数")
    by_status: dict[str, int] = Field(
        default_factory=dict,
        description="按状态分布，如 {'candidate': 20, 'auto_validated': 15, ...}",
    )
    by_type: dict[str, int] = Field(
        default_factory=dict,
        description="按类型分布, 如 {'qa': 30, 'socratic': 10, ...}",
    )
    by_verdict: dict[str, int] = Field(
        default_factory=dict,
        description="按质量门禁分布，如 {'reject': 5, 'needs_careful_review': 10, 'normal_review': 15}",
    )
    avg_quality_score: float = Field(default=0.0, description="平均质量分")
    approval_rate: float = Field(default=0.0, description="审核通过率")
    recent_reviews: list[ReviewRecord] = Field(default_factory=list, description="最近审核记录")


class FeedbackExpansionRequest(BaseModel):
    """
    反馈驱动扩充请求。

    不靠教材主动生成，而是根据学生使用数据发现缺口：
      - 哪些问题经常被问，但 RAG 回答置信度低？
      - 哪些题目错误率最高？
      - 学生最常在哪个苏格拉底步骤卡住？
      - 费曼解释最常缺少哪个因果节点？
    """
    reason: str = Field(..., description="扩充原因：high_error_rate / low_rag_confidence / socratic_stuck / feynman_missing")
    knowledge_id: str = Field(..., description="关联的知识单元 ID")
    observed_issue: str = Field(..., description="观察到的具体问题描述")
    requested_items: dict[str, int] = Field(
        default_factory=dict,
        description="请求的各类数据数量，如 {'qa': 5, 'socratic': 3, 'feynman': 2}",
    )
    source_session_ids: list[str] = Field(
        default_factory=list, description="来源 session ID（脱敏后）"
    )
    created_at: str = Field(default="", description="请求创建时间")
