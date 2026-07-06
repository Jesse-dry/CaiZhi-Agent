"""
Chunk 质量检查脚本。

检查项：
  - 总 chunk 数
  - 空 chunk 数
  - 平均 / 最大 / 最小 长度
  - 缺 metadata 的 chunk 数
  - 每本书 chunk 分布

用法:
    python -m rag.check_chunks
"""

import json
from pathlib import Path
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent.parent
CHUNKS_DIR = BASE_DIR / "data" / "processed" / "chunks"


def load_jsonl(path):
    records = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def check_chunks(path):
    chunks = load_jsonl(path)

    print(f"\n{'='*60}")
    print(f"Checking: {path}")
    print(f"{'='*60}")

    if not chunks:
        print("  ⚠️  No chunks found!")
        return

    print(f"Total chunks: {len(chunks)}")

    # 长度统计
    lengths = [len(c.get("text", "")) for c in chunks]
    empty = [c for c in chunks if not c.get("text", "").strip()]

    print(f"Empty chunks: {len(empty)}  {'⚠️' if len(empty) > 0 else '✅'}")
    print(f"Min length:  {min(lengths)}")
    print(f"Max length:  {max(lengths)}  {'⚠️ 过大' if max(lengths) > 6000 else '✅'}")
    print(f"Avg length:  {sum(lengths) / len(lengths):.1f}  "
          f"{'⚠️ 偏短' if sum(lengths) / len(lengths) < 200 else '⚠️ 偏长' if sum(lengths) / len(lengths) > 3000 else '✅'}")

    # 长度分布
    buckets = {"<200": 0, "200-500": 0, "500-1500": 0, "1500-3000": 0, ">3000": 0}
    for l in lengths:
        if l < 200: buckets["<200"] += 1
        elif l < 500: buckets["200-500"] += 1
        elif l < 1500: buckets["500-1500"] += 1
        elif l < 3000: buckets["1500-3000"] += 1
        else: buckets[">3000"] += 1
    print("\nLength distribution:")
    for k, v in buckets.items():
        pct = v / len(chunks) * 100
        bar = "█" * int(pct / 5)
        print(f"  {k:>10}: {v:>5} ({pct:>5.1f}%) {bar}")

    # 每文档分布
    doc_counter = Counter(c.get("doc_id", "UNKNOWN") for c in chunks)
    print("\nChunks per doc:")
    for doc_id, count in doc_counter.most_common():
        print(f"  {doc_id}: {count}")

    # Metadata 完整性
    required_keys = [
        ("chunk_id", True),
        ("doc_id", True),
        ("file_name", True),
        ("language", True),
        ("text", True),
        ("headers", False),   # 可以为空 dict
        ("chapter", False),   # 可以为 None
        ("section", False),   # 可以为 None
        ("image_captions", False),
    ]

    print("\nMetadata completeness:")
    all_ok = True
    for key, is_required in required_keys:
        missing = [
            c for c in chunks
            if key not in c or (is_required and c.get(key) in [None, ""])
        ]
        status = "✅" if len(missing) == 0 else ("⚠️" if not is_required else "❌")
        if len(missing) > 0 and is_required:
            all_ok = False
        print(f"  {status} {key}: {len(missing)} missing")

    # Headers 覆盖率
    has_h1 = sum(1 for c in chunks if c.get("headers", {}).get("h1"))
    has_h2 = sum(1 for c in chunks if c.get("headers", {}).get("h2"))
    has_h3 = sum(1 for c in chunks if c.get("headers", {}).get("h3"))
    has_any_header = sum(1 for c in chunks if c.get("headers"))

    print(f"\nHeaders coverage:")
    print(f"  Has any header: {has_any_header}/{len(chunks)} ({has_any_header/len(chunks)*100:.1f}%)")
    print(f"  Has h1: {has_h1}/{len(chunks)}")
    print(f"  Has h2: {has_h2}/{len(chunks)}")
    print(f"  Has h3: {has_h3}/{len(chunks)}")

    if has_any_header == 0:
        print(f"  ❌ 没有检测到任何标题！Markdown 解析可能有问题。")
    elif has_any_header < len(chunks) * 0.3:
        print(f"  ⚠️ 标题覆盖率偏低，Markdown 可能缺少清晰的 H1/H2/H3 结构。")

    # 随机抽样
    import random
    print(f"\nRandom samples (5):")
    for c in random.sample(chunks, min(5, len(chunks))):
        headers = c.get("headers", {})
        header_str = " > ".join(v for v in [headers.get("h1"), headers.get("h2"), headers.get("h3")] if v)
        print(f"  [{c['chunk_id']}] {header_str or '(no headers)'}")
        print(f"    length={c.get('chunk_size', len(c.get('text','')))} | "
              f"lang={c.get('language')} | doc={c.get('doc_id')}")
        print(f"    text preview: {c.get('text', '')[:120]}...")
        print()

    if all_ok and len(empty) == 0:
        print("✅ All checks passed!")
    else:
        print("⚠️  Some issues found — review before building vector store.")


def main():
    for name in ["zh_chunks.jsonl", "en_chunks.jsonl"]:
        path = CHUNKS_DIR / name
        if path.exists():
            check_chunks(str(path))
        else:
            print(f"\nNot found: {path}")


if __name__ == "__main__":
    main()
