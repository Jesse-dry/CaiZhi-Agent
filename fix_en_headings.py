"""修复英文教材 Markdown 的标题层级问题"""
import re
from pathlib import Path

PROCESSED = Path(__file__).resolve().parent / "data" / "processed" / "markdown" / "en"
md_file = next(PROCESSED.glob("*.md"))
text = md_file.read_text(encoding="utf-8")
lines = text.splitlines()

fixed_lines = []
changes = {"promoted_to_h1": [], "demoted_formula": [], "cleaned_span": 0,
           "cleaned_bold": 0, "fixed_h3_chapter": []}

for i, line in enumerate(lines):
    m = re.match(r"^(#{1,3})\s+(.*)$", line)
    if not m:
        fixed_lines.append(line)
        continue

    hashes, content = m.group(1), m.group(2)

    # 1. 去掉 <span> 标签
    new_content = re.sub(r'<span[^>]*>|</span>', '', content)
    if new_content != content:
        changes["cleaned_span"] += 1

    # 2. 去掉 ** 标记（保留内部文字）
    new_content = re.sub(r'\*\*([^*]+)\*\*', r'\1', new_content)
    if new_content != content and '**' in content:
        changes["cleaned_bold"] += 1

    # 3. 处理公式碎片 — 不符合正常标题特征的 # 行
    if hashes == '#' and not re.search(r'Chapter|Appendix|chapter', new_content):
        # 检查是否是公式/正文碎片（含数学符号、过短、不像标题）
        if re.search(r'[=+\-*/\\]', new_content) or len(new_content) < 20:
            changes["demoted_formula"].append(new_content[:60])
            fixed_lines.append(new_content)  # 保留文本，去掉 #
            continue

    # 3.5 修复 "C h a p t e r" → "Chapter"（OCR 空格 artifact）
    new_content = re.sub(
        r'\bC\s+h\s+a\s+p\s+t\s+e\s+r\s+(\d+)',
        r'Chapter \1', new_content, flags=re.IGNORECASE
    )

    # 4. 章节升级：Chapter X 或 Appendix → 统一为 #
    chapter_match = re.match(r'(Chapter\s*\d+|Appendix)', new_content, re.IGNORECASE)
    if chapter_match and hashes != '#':
        changes["promoted_to_h1"].append(new_content[:80])
        hashes = '#'

    # 5. H3 章节统一为 H2（非章节的 H3 保持原样）
    if hashes == '###' and chapter_match:
        changes["fixed_h3_chapter"].append(new_content[:80])
        hashes = '##'

    # 6. 修复 OCR 错标：Chapter 5 Diffusion WHY STUDY *Corrosion* → 实为 Ch17 子节
    if re.search(r'Chapter\s*5\s+Diffusion\s+WHY\s+STUDY', new_content, re.IGNORECASE):
        new_content = re.sub(
            r'Chapter\s*5\s+Diffusion\s+', '', new_content, flags=re.IGNORECASE
        ).strip()
        hashes = '##'  # 降级为子节
        changes.setdefault("fixed_ocr_ch5", []).append(new_content[:80])

    # 7. 空格规范化
    new_content = new_content.strip()
    fixed_lines.append(f"{hashes} {new_content}")

# 写回
md_file.write_text('\n'.join(fixed_lines), encoding='utf-8')

# 报告
print("=== 修复报告 ===")
print(f"章节升级为 # (H1): {len(changes['promoted_to_h1'])}")
for h in changes["promoted_to_h1"]:
    print(f"  → {h}")
print(f"\n公式碎片降级: {len(changes['demoted_formula'])}")
for h in changes['demoted_formula']:
    print(f"  → {h}")
print(f"\nH3 章节修正为 H2: {len(changes['fixed_h3_chapter'])}")
for h in changes['fixed_h3_chapter']:
    print(f"  → {h}")
print(f"清理 <span> 标签: {changes['cleaned_span']} 处")
print(f"清理 ** 标记: {changes['cleaned_bold']} 处")
print(f"\n总行数: {len(lines)}, 已写入: {md_file}")
