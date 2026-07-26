#!/usr/bin/env python3
"""
扩充苏格拉底引导链数据集。

用法:
    python scripts/expand_socratic_dataset.py --chain-id C001 --count 5
    python scripts/expand_socratic_dataset.py --knowledge-ids K_QUENCHING,K_MARTENSITE --count 3
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas.generation_blueprint import ExpansionTarget
from services.dataset_expansion_service import create_expansion_service


def main():
    parser = argparse.ArgumentParser(description="扩充苏格拉底引导链数据集")
    parser.add_argument("--knowledge-ids", type=str, default="K_QUENCHING,K_MARTENSITE",
                        help="知识节点 ID，逗号分隔")
    parser.add_argument("--chain-id", type=str, default="C001",
                        help="关联的因果链 ID")
    parser.add_argument("--count", type=int, default=5,
                        help="生成数量")

    args = parser.parse_args()

    knowledge_ids = [k.strip() for k in args.knowledge_ids.split(",")]

    target = ExpansionTarget(
        knowledge_ids=knowledge_ids,
        graph_path_id=args.chain_id,
        output_types=["socratic"],
        target_count=args.count,
        generate_student_answers=False,
    )

    print(f"🎯 扩充苏格拉底链: {knowledge_ids} (chain={args.chain_id})")
    print(f"   生成数量: {args.count}")

    service = create_expansion_service()
    batch = asyncio.run(service.run_full_pipeline(target, use_critic=False))

    print(f"\n✅ 生成完成！")
    print(f"   苏格拉底链: {len(batch.socratic_items)}")
    print(f"   已保存到: data/candidates/socratic_candidates.jsonl")


if __name__ == "__main__":
    main()
