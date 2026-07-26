"""
数据集仓库抽象接口。

定义候选数据、已发布数据、审核记录的 CRUD 操作。
当前实现：JSONL 文件（infrastructure/jsonl_dataset_repo.py）
未来可替换为：SQLite、PostgreSQL
"""

from abc import ABC, abstractmethod
from typing import Any


class DatasetRepository(ABC):
    """数据集仓库抽象接口"""

    # ── 候选数据 ──

    @abstractmethod
    def save_candidate(self, item: dict, item_type: str) -> str:
        """保存单条候选数据，返回文件路径"""
        ...

    @abstractmethod
    def save_candidates(self, items: list[dict], item_type: str) -> str:
        """批量保存候选数据"""
        ...

    @abstractmethod
    def list_candidates(
        self,
        item_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """列出候选数据，支持按类型/状态过滤"""
        ...

    @abstractmethod
    def get_candidate(self, item_id: str, item_type: str | None = None) -> dict | None:
        """获取单条候选数据"""
        ...

    @abstractmethod
    def update_candidate_status(self, item_id: str, status: str, item_type: str) -> bool:
        """更新候选数据状态"""
        ...

    # ── 已发布数据 ──

    @abstractmethod
    def publish_items(
        self, item_ids: list[str], item_type: str, version: str
    ) -> str:
        """发布候选数据到正式数据集，返回发布文件路径"""
        ...

    @abstractmethod
    def list_published(self, item_type: str, version: str | None = None) -> list[dict]:
        """列出已发布数据"""
        ...

    # ── 审核记录 ──

    @abstractmethod
    def save_review(self, review: dict) -> str:
        """保存审核记录"""
        ...

    @abstractmethod
    def list_reviews(self, item_id: str | None = None, limit: int = 50) -> list[dict]:
        """列出审核记录"""
        ...

    # ── 版本管理 ──

    @abstractmethod
    def get_version_info(self, version: str) -> dict | None:
        """获取版本信息"""
        ...

    @abstractmethod
    def list_versions(self, item_type: str | None = None) -> list[dict]:
        """列出所有版本"""
        ...
