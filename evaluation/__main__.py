"""
材智 Agent 自动评测基线 — CLI 入口。

用法:
    python -m evaluation                 # 终端表格输出全部 7 项指标
    python -m evaluation --json          # JSON 输出（CI 集成用）
    python -m evaluation --metric X      # 单指标输出
    python -m evaluation --list          # 列出所有可用指标

可用指标:
    retrieval           双语检索指标
    keypoint_coverage   回答关键点覆盖率
    causal_chain        因果链完整度
    diagnosis           误区诊断准确率
    socratic            苏格拉底引导匹配率
    feynman             费曼评价一致性
    learning_path       学习路径规则正确率
"""

import argparse
import sys

from evaluation.evaluator import Evaluator, METRIC_META


def main() -> None:
    # Windows 终端 UTF-8 兼容
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        prog="python -m evaluation",
        description="材智 Agent 自动评测基线",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出结果",
    )
    parser.add_argument(
        "--metric",
        type=str,
        default=None,
        metavar="KEY",
        help="只运行指定指标（如 retrieval, diagnosis, feynman）",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有可用指标",
    )
    args = parser.parse_args()

    # --list: 列出指标
    if args.list:
        print("可用指标:")
        for key, meta in METRIC_META.items():
            print(f"  {key:<22} {meta['name']}  (权重: {meta['weight']})")
        return

    # 初始化评测器
    print("正在初始化评测器...", file=sys.stderr)
    evaluator = Evaluator()

    # 运行评测
    if args.metric:
        print(f"正在评测: {args.metric} ...", file=sys.stderr)
        result = evaluator.run_one(args.metric)
        if result is None:
            print(f"错误: 未知指标 '{args.metric}'", file=sys.stderr)
            sys.exit(1)
        results = [result]
    else:
        print("正在运行全部 7 项指标...", file=sys.stderr)
        results = evaluator.run_all()

    # 输出
    if args.json:
        print(evaluator.format_json(results))
    else:
        print()
        print(evaluator.format_table(results))


if __name__ == "__main__":
    main()
