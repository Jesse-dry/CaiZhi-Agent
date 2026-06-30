def chunk_text(text: str, chunk_size: int = 500, overlap: int = 80):
    """
    简单按字符切 chunk。
    第一版够用，后面再换成按标题/段落切分。
    """
    assert overlap < chunk_size, "overlap must be less than chunk_size"

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start = end - overlap

        if start <= 0 or start >= len(text):
            break

    return chunks


def build_chunks_from_pages(pages, topic_hint=""):
    """
    pages: pdf_parser.parse_pdf() 的返回值
    """
    all_chunks = []

    for page in pages:
        chunks = chunk_text(page["text"])

        for idx, chunk in enumerate(chunks):
            chunk_id = f"{page['language']}_{page['source_file']}_p{page['page']}_c{idx}"

            all_chunks.append({
                "chunk_id": chunk_id,
                "source_file": page["source_file"],
                "source_path": page["source_path"],
                "language": page["language"],
                "page": page["page"],
                "chunk_index": idx,
                "topic_hint": topic_hint,
                "text": chunk
            })

    return all_chunks
