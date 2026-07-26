#!/usr/bin/env python3
"""
发布候选数据到正式数据集。

用法:
    python scripts/publish_dataset.py --type qa --version 2026.08.1
    python scripts/publish_dataset.py --type qa --version 2026.08.1 --ids Q_AUTO_0001,Q_AUTO_0002
    python scripts/publish_dataset.py --type all --version 2026.08.1 --approved-only
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.dataset_expansion_service import create_expansion_service
from infrastructure.jsonl_dataset_repo import create_jsonl_dataset_repo


def main():
    parser = argparse.ArgumentParser(description="发布数据集")
    parser.add_argument("--type", type=str, required=True,
                        choices=["qa", "student_answer", "socratic", "feynman_task", "feynman_response", "all"],
                        help="数据类型")
    parser.add_argument("--version", type=str, required=True,
                        help="版本号，如 2026.08.1")
    parser.add_argument("--ids", type=str, default=None,
                        help="指定 ID 列表（逗号分隔），不指定则发布所有已批准项")
    parser.add_argument("--approved-only", action="store_true", default=True,
                        help="仅发布已批准的数据（默认开启）")
    parser.add_argument("--publisher", type=str, default="cli",
                        help="发布人标识")

    args = parser.parse_args()

    repo = create_jsonl_dataset_repo()

    async def publish_type(item_type: str):
        if args.ids:
            item_ids = [i.strip() for i in args.ids.split(",")]
        else:
            candidates = repo.list_candidates(
                item_type=item_type,
                status="approved" if args.approved_only else None,
                limit=10000,
            )
            item_ids = [c["id"] for c in candidates]

        if not item_ids:
            print(f"⚠️  {item_type}: 没有可发布的数据")
            return

        print(f"📤 发布 {item_type}: {len(item_ids)} 条")
        filepath = repo.publish_items(item_ids, item_type, args.version)
        print(f"   → {filepath}")

        # 创建版本记录
        from infrastructure.dataset_version_store import create_version_store
        version_store = create_version_store()
        published = repo.list_published(item_type, args.version)
        version_store.create_version(
            version=args.version,
            item_type=item_type,
            item_count=len(published),
            published_by=args.publisher,
        )
        print(f"   版本 v{args.version}: {len(published)} 条已发布数据")

    async def run():
        if args.type == "all":
            for t in ["qa", "socratic", "feynman_task"]:
                await publish_type(t)
        else:
            await publish_type(args.type)

        print(f"\n✅ 发布完成！版本: v{args.version}")

    asyncio.run(run())


if __name__ == "__main__":
    main()
