"""
补全图片索引字段：page、nearby_header、caption_status。
纯文本扫描，不调用任何模型。

用法:
    python -m rag.enrich_images
"""

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MARKDOWN_DIR = BASE_DIR / "data" / "processed" / "markdown"
CHUNKS_DIR = BASE_DIR / "data" / "processed" / "chunks"

HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
PAGE_RE = re.compile(r"_page_(\d+)_")


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def save_jsonl(records: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def extract_page(filename: str) -> int | None:
    m = PAGE_RE.search(filename)
    return int(m.group(1)) if m else None


def build_image_position_index(md_text: str) -> dict[str, str]:
    """
    扫描 Markdown 全文，为每张图片找到最近的标题路径。
    返回 {image_filename: "章节 > 节 > 小节"}。
    """
    # 找所有标题位置：[(char_pos, level, text)]
    headings = [(m.start(), len(m.group(1)), m.group(2).strip())
                for m in HEADING_RE.finditer(md_text)]

    # 找所有图片引用及其位置
    img_pattern = re.compile(r"!\[\]\(([^)]+)\)")
    images = [(m.start(), m.group(1)) for m in img_pattern.finditer(md_text)]

    result = {}
    for img_pos, img_ref in images:
        # 只取文件名，去掉路径前缀
        img_name = Path(img_ref).name

        # 找 img_pos 之前最近的标题链
        h1 = h2 = h3 = ""
        for h_pos, level, text in headings:
            if h_pos > img_pos:
                break
            if level == 1:
                h1, h2, h3 = text, "", ""
            elif level == 2:
                h2, h3 = text, ""
            elif level == 3:
                h3 = text

        parts = [p for p in (h1, h2, h3) if p]
        result[img_name] = " > ".join(parts) if parts else ""

    return result


def enrich(language: str, doc_dir: str, doc_id: str) -> list[dict]:
    """补全一个文档的图片索引"""
    md_path = MARKDOWN_DIR / language / f"{doc_dir}.md" if doc_dir else None

    # 尝试匹配 Markdown 文件
    if md_path and md_path.exists():
        pass
    else:
        # 搜索 Markdown 目录找匹配的 md 文件
        lang_md_dir = MARKDOWN_DIR / language
        candidates = list(lang_md_dir.glob("*.md")) if lang_md_dir.exists() else []
        md_path = candidates[0] if candidates else None

    if not md_path or not md_path.exists():
        print(f"  [WARN] Markdown not found for {language}/{doc_id}")
        return []

    print(f"  Scanning: {md_path.name}")
    md_text = md_path.read_text(encoding="utf-8")
    img_index = build_image_position_index(md_text)
    print(f"  Found {len(img_index)} image references in Markdown")

    # 加载 captions
    captions_path = CHUNKS_DIR / "image_captions.jsonl"
    all_captions = load_jsonl(captions_path)

    updated = 0
    for item in all_captions:
        if item.get("language") != language:
            continue

        img_name = item.get("image_name", "")
        if not img_name:
            continue

        # page
        if not item.get("page"):
            pg = extract_page(img_name)
            if pg is not None:
                item["page"] = pg
                updated += 1

        # nearby_header
        if not item.get("nearby_header"):
            header = img_index.get(img_name, "")
            if header:
                item["nearby_header"] = header
                updated += 1
            elif img_name:
                # 有些图片引用可能带了子目录
                for idx_name, idx_header in img_index.items():
                    if img_name in idx_name or idx_name in img_name:
                        item["nearby_header"] = idx_header
                        updated += 1
                        break

        # caption_status
        if not item.get("caption_status") or item["caption_status"] == "pending":
            has_text = bool(item.get("text", "").strip())
            has_en = bool(item.get("caption_en", "").strip())
            item["caption_status"] = "done" if (has_text or has_en) else "pending"

    # 回写 JSONL
    save_jsonl(all_captions, captions_path)
    return all_captions


def update_chromadb_metadata(items: list[dict]):
    """将 enriched 字段同步到 ChromaDB"""
    import chromadb
    from tqdm import tqdm

    client = chromadb.PersistentClient(path="vector_store/v2_images")
    coll = client.get_collection("materials_images")

    batch_size = 100
    updated = 0
    for i in tqdm(range(0, len(items), batch_size), desc="  Updating ChromaDB"):
        batch = items[i:i + batch_size]
        ids = [item["chunk_id"] for item in batch]
        metadatas = []
        for item in batch:
            metadatas.append({
                "page": item.get("page", 0),
                "nearby_header": item.get("nearby_header", ""),
                "caption_status": item.get("caption_status", ""),
                "related_terms": json.dumps(item.get("related_terms", []), ensure_ascii=False),
            })
        coll.update(ids=ids, metadatas=metadatas)
        updated += len(batch)

    del client
    print(f"  ChromaDB updated: {updated} records")


def main():
    print("=" * 60)
    print("Enrich Image Index (no LLM, text scan only)")
    print("=" * 60)

    all_items = []

    # 中文教材
    zh_items = enrich(
        language="zh",
        doc_dir="材料科学基础_清华",
        doc_id="材料科学基础_清华",
    )
    all_items.extend(zh_items)

    # 英文教材
    en_items = enrich(
        language="en",
        doc_dir="Materials_Science_Engineering_Callister",
        doc_id="Materials_Science_Engineering_Callister",
    )
    all_items.extend(en_items)

    if all_items:
        print(f"\n[Sync] Writing enriched metadata to ChromaDB...")
        update_chromadb_metadata(all_items)

    # 验证
    print("\n[Verify] Sample enriched records:")
    for item in all_items[:3]:
        print(f"  image_name: {item.get('image_name')}")
        print(f"  page: {item.get('page')}")
        print(f"  nearby_header: {item.get('nearby_header')}")
        print(f"  caption_status: {item.get('caption_status')}")
        print()


if __name__ == "__main__":
    main()
