import json
from pathlib import Path

from knowledge.indexing.pdf_parser import parse_pdf
from knowledge.indexing.chunker import build_chunks_from_pages


BASE_DIR = Path(__file__).resolve().parent.parent.parent

ZH_DIR = BASE_DIR / "data" / "textbooks" / "zh"
EN_DIR = BASE_DIR / "data" / "textbooks" / "en"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def save_jsonl(items, path):
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def build_language_chunks(pdf_dir: Path, language: str):
    all_chunks = []

    for pdf_path in pdf_dir.glob("*.pdf"):
        pages = parse_pdf(str(pdf_path), language=language)
        chunks = build_chunks_from_pages(
            pages,
            topic_hint="铁碳相图与钢的热处理"
        )
        all_chunks.extend(chunks)

    return all_chunks


if __name__ == "__main__":
    zh_chunks = build_language_chunks(ZH_DIR, "zh")
    en_chunks = build_language_chunks(EN_DIR, "en")

    save_jsonl(zh_chunks, PROCESSED_DIR / "chunks_zh.jsonl")
    save_jsonl(en_chunks, PROCESSED_DIR / "chunks_en.jsonl")
    save_jsonl(zh_chunks + en_chunks, PROCESSED_DIR / "chunks_all.jsonl")

    print(f"中文 chunks: {len(zh_chunks)}")
    print(f"英文 chunks: {len(en_chunks)}")
    print("Done.")
