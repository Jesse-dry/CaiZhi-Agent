from pathlib import Path
import pymupdf


def parse_pdf(pdf_path: str, language: str):
    """
    把 PDF 按页解析成文本。
    返回 list[dict]。
    """
    pdf_path = Path(pdf_path)
    doc = pymupdf.open(pdf_path)

    pages = []

    for page_index, page in enumerate(doc):
        text = page.get_text("text", sort=True).strip()

        if not text:
            continue

        pages.append({
            "source_file": pdf_path.name,
            "source_path": str(pdf_path),
            "language": language,
            "page": page_index + 1,
            "text": text
        })

    return pages
