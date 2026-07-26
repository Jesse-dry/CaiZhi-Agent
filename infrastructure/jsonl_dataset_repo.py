"""
JSONL 数据集仓库实现。

候选数据以 JSONL 格式存储，每行一条记录，方便：
  - 逐行追加（不需要重写整个文件）
  - 流式读取（不需要全量加载到内存）
  - 用 git diff 追踪变更

目录结构：
  data/candidates/{type}_candidates.jsonl   — 候选数据
  data/reviewed/{type}_reviewed.jsonl       — 已审核
  data/rejected/{type}_rejected.jsonl       — 已拒绝
  data/published/v{version}/{type}.json     — 已发布（标准 JSON 数组）
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from repositories.dataset_repo import DatasetRepository

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# 文件路径映射
CANDIDATE_FILES = {
    "qa": DATA_DIR / "candidates" / "qa_candidates.jsonl",
    "student_answer": DATA_DIR / "candidates" / "student_answers.jsonl",
    "socratic": DATA_DIR / "candidates" / "socratic_candidates.jsonl",
    "feynman_task": DATA_DIR / "candidates" / "feynman_candidates.jsonl",
    "feynman_response": DATA_DIR / "candidates" / "feynman_responses.jsonl",
}

REVIEWED_FILES = {
    "qa": DATA_DIR / "reviewed" / "qa_reviewed.jsonl",
    "student_answer": DATA_DIR / "reviewed" / "student_answers_reviewed.jsonl",
    "socratic": DATA_DIR / "reviewed" / "socratic_reviewed.jsonl",
    "feynman_task": DATA_DIR / "reviewed" / "feynman_reviewed.jsonl",
    "feynman_response": DATA_DIR / "reviewed" / "feynman_responses_reviewed.jsonl",
}

REJECTED_FILES = {
    "qa": DATA_DIR / "rejected" / "qa_rejected.jsonl",
    "student_answer": DATA_DIR / "rejected" / "student_answers_rejected.jsonl",
    "socratic": DATA_DIR / "rejected" / "socratic_rejected.jsonl",
    "feynman_task": DATA_DIR / "rejected" / "feynman_rejected.jsonl",
    "feynman_response": DATA_DIR / "rejected" / "feynman_responses_rejected.jsonl",
}

REVIEW_LOG_PATH = DATA_DIR / "review_log.jsonl"


def _ensure_dir(filepath: Path) -> None:
    """确保文件所在目录存在"""
    filepath.parent.mkdir(parents=True, exist_ok=True)


def _read_jsonl(filepath: Path) -> list[dict]:
    """读取 JSONL 文件的所有行"""
    if not filepath.exists():
        return []
    items: list[dict] = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning(f"Skipping invalid JSON line in {filepath}")
    return items


def _append_jsonl(filepath: Path, items: list[dict]) -> None:
    """追加多条记录到 JSONL 文件"""
    _ensure_dir(filepath)
    with open(filepath, "a", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _write_jsonl(filepath: Path, items: list[dict]) -> None:
    """覆写 JSONL 文件"""
    _ensure_dir(filepath)
    with open(filepath, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


class JsonlDatasetRepo(DatasetRepository):
    """JSONL 文件数据集仓库"""

    def __init__(self, data_dir: Path | None = None):
        self._data_dir = data_dir or DATA_DIR

    # ── 候选数据 ──

    def save_candidate(self, item: dict, item_type: str) -> str:
        """保存单条候选数据"""
        filepath = CANDIDATE_FILES.get(item_type)
        if filepath is None:
            raise ValueError(f"Unknown item_type: {item_type}")
        _append_jsonl(filepath, [item])
        return str(filepath)

    def save_candidates(self, items: list[dict], item_type: str) -> str:
        """批量保存候选数据"""
        filepath = CANDIDATE_FILES.get(item_type)
        if filepath is None:
            raise ValueError(f"Unknown item_type: {item_type}")
        _append_jsonl(filepath, items)
        return str(filepath)

    def list_candidates(
        self,
        item_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """列出候选数据"""
        if item_type:
            filepaths = [CANDIDATE_FILES.get(item_type)]
            if filepaths[0] is None:
                return []
        else:
            filepaths = list(CANDIDATE_FILES.values())

        all_items: list[dict] = []
        for fp in filepaths:
            all_items.extend(_read_jsonl(fp))

        # 按状态过滤
        if status:
            all_items = [i for i in all_items if i.get("status") == status]

        return all_items[offset:offset + limit]

    def get_candidate(self, item_id: str, item_type: str | None = None) -> dict | None:
        """获取单条候选数据"""
        if item_type:
            filepaths = [CANDIDATE_FILES.get(item_type)]
            if filepaths[0] is None:
                return None
        else:
            filepaths = list(CANDIDATE_FILES.values())

        for fp in filepaths:
            for item in _read_jsonl(fp):
                if item.get("id") == item_id:
                    return item
        return None

    def update_candidate_status(self, item_id: str, status: str, item_type: str) -> bool:
        """更新候选数据状态（重写整个文件）"""
        filepath = CANDIDATE_FILES.get(item_type)
        if filepath is None:
            return False

        items = _read_jsonl(filepath)
        found = False
        for item in items:
            if item.get("id") == item_id:
                item["status"] = status
                found = True
                break

        if found:
            _write_jsonl(filepath, items)
        return found

    # ── 已发布数据 ──

    def publish_items(
        self, item_ids: list[str], item_type: str, version: str
    ) -> str:
        """发布候选数据到正式数据集"""
        # 从候选文件中读取指定 ID 的条目
        filepath = CANDIDATE_FILES.get(item_type)
        if filepath is None:
            raise ValueError(f"Unknown item_type: {item_type}")

        all_candidates = _read_jsonl(filepath)
        to_publish = [
            c for c in all_candidates
            if c.get("id") in item_ids and c.get("status") == "approved"
        ]

        # 标记为 published
        for item in to_publish:
            item["status"] = "published"
            item["dataset_version"] = version
            item["approved_at"] = item.get("approved_at") or datetime.now(UTC).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

        # 写入正式数据集
        publish_dir = DATA_DIR / "published" / f"v{version}"
        _ensure_dir(publish_dir)
        publish_path = publish_dir / f"{item_type}.json"

        # 读取已有发布数据（如果存在）
        existing: list[dict] = []
        if publish_path.exists():
            with open(publish_path, "r", encoding="utf-8") as f:
                existing = json.load(f)

        # 合并（以 ID 去重）
        existing_ids = {item.get("id") for item in existing}
        new_items = [item for item in to_publish if item.get("id") not in existing_ids]
        existing.extend(new_items)

        with open(publish_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        # 同时转为 JSONL 保存到 reviewed/
        reviewed_path = REVIEWED_FILES.get(item_type)
        if reviewed_path:
            _append_jsonl(reviewed_path, to_publish)

        logger.info(
            f"Published {len(new_items)} items to {publish_path} "
            f"(total published: {len(existing)})"
        )
        return str(publish_path)

    def list_published(self, item_type: str, version: str | None = None) -> list[dict]:
        """列出已发布数据"""
        if version:
            publish_dir = DATA_DIR / "published" / f"v{version}"
        else:
            # 找最新版本
            publish_base = DATA_DIR / "published"
            if not publish_base.exists():
                return []
            versions = sorted(
                [d.name for d in publish_base.iterdir() if d.is_dir()],
                reverse=True,
            )
            if not versions:
                return []
            publish_dir = publish_base / versions[0]

        publish_path = publish_dir / f"{item_type}.json"
        if not publish_path.exists():
            return []

        with open(publish_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── 审核记录 ──

    def save_review(self, review: dict) -> str:
        """保存审核记录"""
        _append_jsonl(REVIEW_LOG_PATH, [review])
        return str(REVIEW_LOG_PATH)

    def list_reviews(self, item_id: str | None = None, limit: int = 50) -> list[dict]:
        """列出审核记录"""
        reviews = _read_jsonl(REVIEW_LOG_PATH)
        if item_id:
            reviews = [r for r in reviews if r.get("item_id") == item_id]
        return reviews[-limit:]  # 最新的在前

    # ── 版本管理 ──

    def get_version_info(self, version: str) -> dict | None:
        """获取版本信息"""
        version_path = DATA_DIR / "published" / f"v{version}" / "_version.json"
        if not version_path.exists():
            return None
        with open(version_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_versions(self, item_type: str | None = None) -> list[dict]:
        """列出所有版本"""
        publish_base = DATA_DIR / "published"
        if not publish_base.exists():
            return []

        versions: list[dict] = []
        for version_dir in sorted(publish_base.iterdir(), reverse=True):
            if not version_dir.is_dir():
                continue
            version_path = version_dir / "_version.json"
            if version_path.exists():
                with open(version_path, "r", encoding="utf-8") as f:
                    versions.append(json.load(f))
            else:
                # 从目录名推断
                versions.append({
                    "version": version_dir.name.replace("v", ""),
                    "item_type": item_type or "unknown",
                })

        return versions

    # ── 工具方法 ──

    def count_candidates(self, item_type: str | None = None, status: str | None = None) -> int:
        """统计候选数据数量"""
        return len(self.list_candidates(item_type=item_type, status=status, limit=100000))

    def reject_candidate(self, item_id: str, item_type: str, reason: str = "") -> bool:
        """拒绝候选数据：从 candidates 移到 rejected"""
        filepath = CANDIDATE_FILES.get(item_type)
        if filepath is None:
            return False

        items = _read_jsonl(filepath)
        rejected_item = None
        remaining = []

        for item in items:
            if item.get("id") == item_id:
                item["status"] = "rejected"
                item["rejection_reason"] = reason
                rejected_item = item
            else:
                remaining.append(item)

        if rejected_item is None:
            return False

        # 重写候选文件（移除已拒绝项）
        _write_jsonl(filepath, remaining)

        # 追加到拒绝文件
        rejected_path = REJECTED_FILES.get(item_type)
        if rejected_path:
            _append_jsonl(rejected_path, [rejected_item])

        return True


def create_jsonl_dataset_repo() -> JsonlDatasetRepo:
    """工厂函数"""
    return JsonlDatasetRepo()
