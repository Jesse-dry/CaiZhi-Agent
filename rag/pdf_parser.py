"""
PDF → Markdown 转换，使用 Marker (surya OCR)。

输出目录结构：
    data/processed/
      markdown/
        zh/{doc_id}.md
        en/{doc_id}.md
      images/
        zh/{doc_id}/page_001_img_001.png
        en/{doc_id}/page_001_img_001.png
"""

from io import BytesIO
from pathlib import Path
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"


def convert_pdf(pdf_path: str, language: str) -> dict:
    """
    用 Marker 将单个 PDF 转为 Markdown，同时提取图片。

    返回:
        {
            "doc_id": "材料科学基础_清华",
            "language": "zh",
            "markdown_path": "data/processed/markdown/zh/材料科学基础_清华.md",
            "images_dir": "data/processed/images/zh/材料科学基础_清华/",
            "image_files": [...],
        }
    """
    pdf_path = Path(pdf_path)
    doc_id = pdf_path.stem

    # Markdown 输出
    md_dir = PROCESSED_DIR / "markdown" / language
    md_dir.mkdir(parents=True, exist_ok=True)

    # 图片输出
    images_dir = PROCESSED_DIR / "images" / language / doc_id
    images_dir.mkdir(parents=True, exist_ok=True)

    print(f"[Marker] Converting: {pdf_path.name} ({language})")

    converter = PdfConverter(artifact_dict=create_model_dict())
    rendered = converter(str(pdf_path))

    # 保存 Markdown
    md_path = md_dir / f"{doc_id}.md"
    md_path.write_text(rendered.markdown, encoding="utf-8")

    # 保存提取的图片（Marker 将图片放在 rendered.images 字典中）
    image_files = []
    for img_name, img_data in rendered.images.items():
        # Marker 图片名格式通常为 "page_001_img_001.png"
        img_path = images_dir / img_name
        if hasattr(img_data, 'save'):
            # Marker >=1.10 返回 PIL Image 对象
            buf = BytesIO()
            img_data.save(buf, format='PNG')
            img_path.write_bytes(buf.getvalue())
        else:
            # 旧版返回 bytes
            img_path.write_bytes(img_data)
        image_files.append({
            "file_name": img_name,
            "path": str(img_path),
        })

    print(f"  → Markdown: {md_path}")
    print(f"  → Images: {len(image_files)} extracted to {images_dir}")

    return {
        "doc_id": doc_id,
        "language": language,
        "markdown_path": str(md_path),
        "images_dir": str(images_dir),
        "image_files": image_files,
    }


def convert_folder(folder_path: str, language: str) -> list[dict]:
    """批量转换文件夹内所有 PDF"""
    folder = Path(folder_path)
    results = []

    for pdf_file in sorted(folder.glob("*.pdf")):
        result = convert_pdf(str(pdf_file), language)
        results.append(result)

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        # 默认跑全量
        zh_dir = BASE_DIR / "data" / "textbooks" / "zh"
        en_dir = BASE_DIR / "data" / "textbooks" / "en"

        for d, lang in [(zh_dir, "zh"), (en_dir, "en")]:
            if d.exists() and list(d.glob("*.pdf")):
                convert_folder(str(d), lang)
    else:
        pdf_path = sys.argv[1]
        language = sys.argv[2] if len(sys.argv) > 2 else "zh"
        convert_pdf(pdf_path, language)
