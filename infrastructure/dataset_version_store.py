"""
数据集版本存储。

管理已发布数据集的版本历史，支持版本对比和回滚。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PUBLISHED_DIR = DATA_DIR / "published"


class DatasetVersionStore:
    """数据集版本管理"""

    def __init__(self, published_dir: Path | None = None):
        self._published_dir = published_dir or PUBLISHED_DIR

    def create_version(
        self,
        version: str,
        item_type: str,
        item_count: int,
        published_by: str = "",
        previous_version: str | None = None,
        changelog: str = "",
    ) -> dict:
        """
        创建新版本记录。

        在发布目录下写入 _version.json 元信息。
        """
        version_dir = self._published_dir / f"v{version}"
        version_dir.mkdir(parents=True, exist_ok=True)

        version_info = {
            "version": version,
            "item_type": item_type,
            "item_count": item_count,
            "published_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "published_by": published_by,
            "previous_version": previous_version,
            "changelog": changelog,
        }

        version_path = version_dir / "_version.json"
        with open(version_path, "w", encoding="utf-8") as f:
            json.dump(version_info, f, ensure_ascii=False, indent=2)

        logger.info(f"Created dataset version: v{version} ({item_type}, {item_count} items)")
        return version_info

    def get_version(self, version: str) -> dict | None:
        """获取指定版本信息"""
        version_path = self._published_dir / f"v{version}" / "_version.json"
        if not version_path.exists():
            return None
        with open(version_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_versions(self, item_type: str | None = None) -> list[dict]:
        """列出所有版本"""
        if not self._published_dir.exists():
            return []

        versions: list[dict] = []
        for version_dir in sorted(self._published_dir.iterdir(), reverse=True):
            if not version_dir.is_dir() or not version_dir.name.startswith("v"):
                continue

            version_path = version_dir / "_version.json"
            if version_path.exists():
                with open(version_path, "r", encoding="utf-8") as f:
                    info = json.load(f)
                    if item_type is None or info.get("item_type") == item_type:
                        versions.append(info)
            else:
                # 从目录名推断
                versions.append({
                    "version": version_dir.name.replace("v", ""),
                    "item_type": "unknown",
                    "item_count": 0,
                })

        return versions

    def get_latest_version(self, item_type: str | None = None) -> dict | None:
        """获取最新版本"""
        versions = self.list_versions(item_type=item_type)
        return versions[0] if versions else None

    def diff_versions(self, version_a: str, version_b: str, item_type: str) -> dict:
        """
        对比两个版本之间的差异。

        返回:
            {
                "added": [...],     # version_b 有, version_a 没有的条目
                "removed": [...],   # version_a 有，version_b 没有的条目
                "modified": [...],  # 两版都有但内容不同的条目
                "unchanged": int,   # 未改变的条目数
            }
        """
        def _load_version(v: str) -> list[dict]:
            path = self._published_dir / f"v{v}" / f"{item_type}.json"
            if not path.exists():
                return []
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

        items_a = {item["id"]: item for item in _load_version(version_a)}
        items_b = {item["id"]: item for item in _load_version(version_b)}

        ids_a = set(items_a.keys())
        ids_b = set(items_b.keys())

        added = [items_b[i] for i in (ids_b - ids_a)]
        removed = [items_a[i] for i in (ids_a - ids_b)]

        modified: list[dict] = []
        unchanged = 0
        for item_id in ids_a & ids_b:
            if items_a[item_id] != items_b[item_id]:
                modified.append({"id": item_id, "old": items_a[item_id], "new": items_b[item_id]})
            else:
                unchanged += 1

        return {
            "added": added,
            "removed": removed,
            "modified": modified,
            "unchanged": unchanged,
        }


def create_version_store() -> DatasetVersionStore:
    """工厂函数"""
    return DatasetVersionStore()
