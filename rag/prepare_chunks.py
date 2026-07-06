"""
RAG 数据预处理管线。

流程：
  1. PDF → Markdown + 图片提取（Marker）
  2. Markdown → 语义 Chunks（MarkdownHeaderTextSplitter）
  3. 保存 JSONL 到 data/processed/chunks/

用法:
    python -m rag.prepare_chunks              # 全量
    python -m rag.prepare_chunks --pdf-only    # 只做 PDF→Markdown
    python -m rag.prepare_chunks --chunk-only  # 只做 Markdown→Chunks
"""

import json
import sys
from pathlib import Path

from rag.pdf_parser import convert_folder
from rag.chunker import build_chunks_from_markdown

# ============================================================
# 开关
# ============================================================
ENABLE_IMAGE_CAPTION = False  # 第一轮先关掉，先验证纯文本管线
MAX_CAPTION_IMAGES = 10       # 打开后也只跑 10 张

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
MARKDOWN_DIR = PROCESSED_DIR / "markdown"
IMAGES_DIR = PROCESSED_DIR / "images"
CHUNKS_DIR = PROCESSED_DIR / "chunks"


def save_jsonl(records: list[dict], output_path: str):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"  → Saved {len(records)} records to {output_path}")


def step_pdf_to_markdown(pdf_dir: str, language: str) -> list[dict]:
    """Step 1: PDF → Markdown + 图片提取"""
    print(f"\n{'='*60}")
    print(f"[Step 1] PDF → Markdown ({language})")
    print(f"{'='*60}")

    results = convert_folder(pdf_dir, language)

    for r in results:
        print(f"  {r['doc_id']}: {len(r['image_files'])} images")

    return results


def step_markdown_to_chunks(pdf_results: list[dict], language: str,
                            chunk_size: int = 1000) -> list[dict]:
    """Step 2: Markdown → 语义 Chunks"""
    print(f"\n[Step 2] Markdown → Semantic Chunks ({language})")

    all_chunks = []

    for pdf_result in pdf_results:
        doc_id = pdf_result["doc_id"]
        file_name = f"{doc_id}.pdf"

        chunks = build_chunks_from_markdown(
            md_path=pdf_result["markdown_path"],
            doc_id=doc_id,
            language=language,
            file_name=file_name,
            max_chunk_size=chunk_size,
            overlap=100,
        )
        all_chunks.extend(chunks)
        print(f"  {file_name}: {len(chunks)} chunks")

    return all_chunks


def process_language(pdf_dir: str, language: str,
                     pdf_only: bool = False,
                     chunk_only: bool = False,
                     chunk_size: int = 1000) -> list[dict]:
    """处理单个语种的完整管线"""

    if chunk_only:
        # 从已有的 Markdown 文件找
        md_lang_dir = MARKDOWN_DIR / language
        if not md_lang_dir.exists():
            print(f"[Error] Markdown dir not found: {md_lang_dir}")
            return []

        pdf_results = []
        for md_file in sorted(md_lang_dir.glob("*.md")):
            doc_id = md_file.stem
            images_dir = IMAGES_DIR / language / doc_id
            pdf_results.append({
                "doc_id": doc_id,
                "language": language,
                "markdown_path": str(md_file),
                "images_dir": str(images_dir),
                "image_files": [],
            })
    else:
        pdf_results = step_pdf_to_markdown(pdf_dir, language)

    if pdf_only:
        return []

    chunks = step_markdown_to_chunks(pdf_results, language, chunk_size=chunk_size)

    # Step 3: 保存
    print(f"\n[Step 3] Save chunks ({language})")
    output_path = CHUNKS_DIR / f"{language}_chunks.jsonl"
    save_jsonl(chunks, str(output_path))

    if ENABLE_IMAGE_CAPTION and pdf_results:
        print(f"\n[Step 4] Image Caption (disabled={not ENABLE_IMAGE_CAPTION})")
        # TODO: 后续打开

    return chunks


def main():
    args = set(sys.argv[1:])
    pdf_only = "--pdf-only" in args
    chunk_only = "--chunk-only" in args

    zh_dir = BASE_DIR / "data" / "textbooks" / "zh"
    en_dir = BASE_DIR / "data" / "textbooks" / "en"

    total_zh = 0
    total_en = 0

    if zh_dir.exists() and list(zh_dir.glob("*.pdf")):
        zh_chunks = process_language(
            str(zh_dir), "zh",
            pdf_only=pdf_only, chunk_only=chunk_only, chunk_size=1000,
        )
        total_zh = len(zh_chunks)

    if en_dir.exists() and list(en_dir.glob("*.pdf")):
        en_chunks = process_language(
            str(en_dir), "en",
            pdf_only=pdf_only, chunk_only=chunk_only, chunk_size=1200,
        )
        total_en = len(en_chunks)

    print(f"\n{'='*60}")
    print(f"Done! zh={total_zh} chunks, en={total_en} chunks")
    if not pdf_only:
        print(f"Chunks dir: {CHUNKS_DIR}")
        print(f"Next: python -m rag.check_chunks")
    if not chunk_only and not pdf_only:
        print(f"(Build vector store after manual review)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
