#!/usr/bin/env python3
"""
扩充 QA 数据集。

用法:
    python scripts/expand_qa_dataset.py --knowledge-ids K_QUENCHING,K_MARTENSITE --count 20
    python scripts/expand_qa_dataset.py --knowledge-ids K_QUENCHING --count 10 --no-student-answers
    python scripts/expand_qa_dataset.py --chain-id C001 --count 15 --difficulty 2
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas.generation_blueprint import ExpansionTarget
from services.dataset_expansion_service import create_expansion_service


def main():
    parser = argparse.ArgumentParser(description="扩充 QA 数据集")
    parser.add_argument("--knowledge-ids", type=str, required=True,
                        help="知识节点 ID，逗号分隔，如 K_QUENCHING,K_MARTENSITE")
    parser.add_argument("--chain-id", type=str, default="C001",
                        help="关联的因果链 ID")
    parser.add_argument("--count", type=int, default=10,
                        help="生成数量")
    parser.add_argument("--difficulty", type=int, nargs="+", default=[1, 2, 3],
                        help="难度分布，如 1 2 3")
    parser.add_argument("--no-student-answers", action="store_true",
                        help="不生成分级学生答案")
    parser.add_argument("--types", type=str, nargs="+",
                        default=["definition", "causal_reasoning", "comparison",
                                 "conditional", "reverse_reasoning", "application_transfer"],
                        help="题型列表")
    parser.add_argument("--output", type=str, default=None,
                        help="输出文件路径（默认追加到 data/candidates/qa_candidates.jsonl）")

    args = parser.parse_args()

    knowledge_ids = [k.strip() for k in args.knowledge_ids.split(",")]

    # 构建难度分布
    diff_dist = {}
    for d in args.difficulty:
        diff_dist[d] = diff_dist.get(d, 0) + 1
    total = sum(diff_dist.values())
    diff_dist = {k: v / total for k, v in diff_dist.items()}

    # 构建题型分布
    type_dist = {t: 1.0 / len(args.types) for t in args.types}

    output_types = ["qa"]
    if not args.no_student_answers:
        output_types.append("student_answers")

    target = ExpansionTarget(
        knowledge_ids=knowledge_ids,
        graph_path_id=args.chain_id,
        output_types=output_types,
        target_count=args.count,
        difficulty_distribution=diff_dist,
        question_type_distribution=type_dist,
        generate_student_answers=not args.no_student_answers,
        answers_per_question=5,
    )

    print(f"🎯 扩充目标: {knowledge_ids}")
    print(f"   题型分布: {type_dist}")
    print(f"   难度分布: {diff_dist}")
    print(f"   生成数量: {args.count}")
    print(f"   学生答案: {'是' if not args.no_student_answers else '否'}")
    print()

    service = create_expansion_service()

    async def run():
        batch = await service.run_full_pipeline(target, use_critic=False)
        return batch

    batch = asyncio.run(run())

    print(f"\n✅ 生成完成！")
    print(f"   QA 题目: {len(batch.qa_items)}")
    print(f"   学生答案: {len(batch.student_answers)}")
    print(f"   已保存到: data/candidates/")


if __name__ == "__main__":
    main()
