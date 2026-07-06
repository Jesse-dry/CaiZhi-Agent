"""
语义分块：基于 Markdown 标题层级切分。

使用 LangChain 的 MarkdownHeaderTextSplitter：
- 按 H1(#), H2(##), H3(###) 层级切分
- 每个 chunk 自带章节 metadata
- chunk 格式对齐规范：

{
  "chunk_id": "zh_材料科学基础_清华_c1",
  "doc_id": "材料科学基础_清华",
  "file_name": "材料科学基础_清华.pdf",
  "language": "zh",
  "page_start": null,
  "page_end": null,
  "chapter": "Chapter 1",
  "section": "1.1 Intro",
  "headers": {"h1": "...", "h2": "...", "h3": "..."},
  "text": "...",
  "image_captions": []
}
"""

from pathlib import Path
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_text_splitters import RecursiveCharacterTextSplitter

HEADERS_TO_SPLIT_ON = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
]

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100


def _extract_chapter_section(headers: dict) -> tuple:
    """从 headers 字典提取 chapter/section 字符串"""
    chapter = headers.get("h1", "")
    section = headers.get("h2", "")
    if not section:
        section = headers.get("h3", "")
    return chapter or None, section or None


def split_markdown(
    markdown_text: str,
    headers: list = None,
) -> list[dict]:
    """按 Markdown 标题层级切分"""
    if headers is None:
        headers = HEADERS_TO_SPLIT_ON

    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers,
        strip_headers=False,
    )

    docs = splitter.split_text(markdown_text)

    chunks = []
    for doc in docs:
        text = doc.page_content.strip()
        if not text:
            continue

        chunks.append({
            "text": text,
            "headers": dict(doc.metadata),
        })

    return chunks


def split_markdown_with_limit(
    markdown_text: str,
    max_chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    headers: list = None,
) -> list[dict]:
    """
    先按标题层级切分，再对过大的 section 按段落二次切分。
    二次切分后的 chunk 继承父级 headers。
    """
    if headers is None:
        headers = HEADERS_TO_SPLIT_ON

    header_chunks = split_markdown(markdown_text, headers)

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", ". ", " ", ""],
    )

    final_chunks = []

    for chunk in header_chunks:
        if len(chunk["text"]) <= max_chunk_size:
            final_chunks.append(chunk)
        else:
            sub_texts = text_splitter.split_text(chunk["text"])
            for sub_text in sub_texts:
                text = sub_text.strip()
                if text:
                    final_chunks.append({
                        "text": text,
                        "headers": dict(chunk["headers"]),
                    })

    return final_chunks


def build_chunks_from_markdown(
    md_path: str,
    doc_id: str,
    language: str,
    file_name: str,
    max_chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    """
    读取 Markdown 文件 → 语义切分 → 返回规范化 chunk 列表。
    """
    md_text = Path(md_path).read_text(encoding="utf-8")
    header_chunks = split_markdown_with_limit(
        md_text,
        max_chunk_size=max_chunk_size,
        overlap=overlap,
    )

    all_chunks = []

    for idx, chunk in enumerate(header_chunks):
        headers = chunk["headers"]
        chapter, section = _extract_chapter_section(headers)

        chunk_id = f"{language}_{doc_id}_c{idx + 1}"

        all_chunks.append({
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "file_name": file_name,
            "language": language,
            "page_start": None,
            "page_end": None,
            "chapter": chapter,
            "section": section,
            "headers": headers,
            "chunk_index": idx + 1,
            "chunk_size": len(chunk["text"]),
            "text": chunk["text"],
            "image_captions": [],
        })

    return all_chunks
