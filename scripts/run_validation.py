#!/usr/bin/env python3
"""
对候选数据运行自动校验。

用法:
    python scripts/run_validation.py --type qa
    python scripts/run_validation.py --type all --status candidate
    python scripts/run_validation.py --input data/candidates/qa_candidates.jsonl
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.dataset_expansion_service import create_expansion_service


def main():
    parser = argparse.ArgumentParser(description="校验候选数据集")
    parser.add_argument("--type", type=str, default="qa",
                        choices=["qa", "student_answer", "socratic", "feynman_task", "feynman_response", "all"],
                        help="数据类型")
    parser.add_argument("--status", type=str, default="candidate",
                        help="按状态过滤")
    parser.add_argument("--input", type=str, default=None,
                        help="直接指定 JSONL 文件路径（绕过 type 参数）")
    parser.add_argument("--output", type=str, default=None,
                        help="输出校验报告路径（JSON）")

    args = parser.parse_args()

    service = create_expansion_service()

    async def run():
        if args.type == "all":
            reports = []
            for t in ["qa", "student_answer", "socratic", "feynman_task", "feynman_response"]:
                print(f"\n🔍 校验 {t}...")
                batch_report = await service.validate_candidates(item_type=t, status=args.status)
                reports.append(batch_report)
                print(f"   总数: {batch_report.total_items}")
                print(f"   通过: {batch_report.passed}")
                print(f"   可发布: {batch_report.publishable}")
                print(f"   通过率: {batch_report.pass_rate}%")
            return reports
        else:
            print(f"🔍 校验 {args.type} (status={args.status})...")
            batch_report = await service.validate_candidates(item_type=args.type, status=args.status)
            print(f"   总数: {batch_report.total_items}")
            print(f"   通过: {batch_report.passed}")
            print(f"   可发布: {batch_report.publishable}")
            print(f"   通过率: {batch_report.pass_rate}%")

            # 显示失败的详情
            for report in batch_report.reports:
                if not report.all_checks_passed:
                    print(f"\n   ❌ {report.item_id}:")
                    for err in report.errors[:5]:
                        print(f"      - {err}")

            if args.output:
                output_path = Path(args.output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(
                        batch_report.model_dump(mode="json"),
                        f, ensure_ascii=False, indent=2, default=str,
                    )
                print(f"\n📄 报告已保存到: {args.output}")

            return batch_report

    asyncio.run(run())


if __name__ == "__main__":
    main()
