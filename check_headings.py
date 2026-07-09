"""提取 .md 文件中所有 #、##、### 标题行"""
import re, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # fix Windows GBK issue
PROCESSED = Path(__file__).resolve().parent / "data" / "processed" / "markdown"

for md_file in sorted(PROCESSED.rglob("*.md")):
    print(f"\n{'='*60}")
    print(f"  {md_file.relative_to(PROCESSED)}")
    print(f"{'='*60}")
    for line in md_file.read_text(encoding="utf-8").splitlines():
        if re.match(r"^#{1,3}\s", line):
            print(line)
