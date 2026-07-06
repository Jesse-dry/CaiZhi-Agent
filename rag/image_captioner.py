"""
图片 Caption 生成：调用视觉大模型为教材图表生成文字描述。

原则：
  - 第一轮默认关闭（prepare_chunks.py 中 ENABLE_IMAGE_CAPTION = False）
  - 打开后限制 MAX_CAPTION_IMAGES = 10
  - 宁可少说，不要编造
"""

import json
import base64
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"

MAX_CAPTION_IMAGES = 10

# 材料学专用 prompt：宁可少说，不要编造
CAPTION_PROMPT = """你是材料科学教材图表解析助手。请用中文描述这张教材图片。

重点说明：
1. 图中展示的材料学对象或曲线是什么（相图/TTT曲线/CCT曲线/金相组织/表格/示意图等）
2. 涉及哪些关键术语（中英文）
3. 如果是相图、TTT/CCT曲线或组织图，请解释坐标轴、区域、相变路径或组织特征
4. 不要编造图中没有的信息
5. 输出 100–200 字

格式：
【图表类型】...
【描述】...
【关键术语】term1, term2, ...
"""


def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_media_type(image_path: str) -> str:
    ext = Path(image_path).suffix.lower()
    mapping = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return mapping.get(ext, "image/png")


def caption_image(image_path: str, client: Anthropic = None) -> dict:
    """
    用 Claude Vision 为单张图片生成描述。

    返回:
        {
            "image_path": "...",
            "caption_zh": "...",
            "caption_en": "",
            "related_terms": [...],
            "confidence": "medium"
        }
    """
    if client is None:
        client = Anthropic()

    base64_image = encode_image(image_path)
    media_type = get_media_type(image_path)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64_image,
                    }
                },
                {"type": "text", "text": CAPTION_PROMPT}
            ]
        }]
    )

    caption_text = message.content[0].text

    # 简单解析：提取关键术语
    related_terms = []
    for line in caption_text.split("\n"):
        if "关键术语" in line:
            terms_part = line.split("】")[-1] if "】" in line else line.split("：")[-1]
            related_terms = [t.strip() for t in terms_part.replace("，", ",").split(",") if t.strip()]
            break

    return {
        "image_path": image_path,
        "caption_zh": caption_text,
        "caption_en": "",
        "related_terms": related_terms,
        "confidence": "medium",
    }


def caption_folder(
    images_dir: str,
    doc_id: str,
    language: str,
    file_name: str = "",
    client: Anthropic = None,
    max_images: int = MAX_CAPTION_IMAGES,
) -> list[dict]:
    """
    为一个文档目录生成 captions（限制数量）。

    返回 list[dict]，每条是可直接入库的 chunk 格式。
    """
    images_dir = Path(images_dir)

    if not images_dir.exists():
        print(f"[Captioner] Images dir not found: {images_dir}")
        return []

    image_files = sorted([
        f for f in images_dir.glob("*")
        if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp")
    ])

    if not image_files:
        print(f"[Captioner] No images found in {images_dir}")
        return []

    # 限制数量
    if len(image_files) > max_images:
        print(f"[Captioner] Limiting to {max_images}/{len(image_files)} images")
        image_files = image_files[:max_images]

    if client is None:
        client = Anthropic()

    if not file_name:
        file_name = f"{doc_id}.pdf"

    captions = []

    for idx, img_path in enumerate(image_files, start=1):
        print(f"[Captioner] ({idx}/{len(image_files)}) {img_path.name}")

        try:
            result = caption_image(str(img_path), client=client)
        except Exception as e:
            print(f"  ⚠️ Failed: {e}")
            result = {
                "image_path": str(img_path),
                "caption_zh": f"[Caption failed: {e}]",
                "caption_en": "",
                "related_terms": [],
                "confidence": "low",
            }

        image_id = f"{language}_{doc_id}_{img_path.stem}"

        captions.append({
            "image_id": image_id,
            "file_name": file_name,
            "doc_id": doc_id,
            "language": language,
            "image_path": result["image_path"],
            "image_name": img_path.name,
            "caption_zh": result["caption_zh"],
            "caption_en": result.get("caption_en", ""),
            "related_terms": result.get("related_terms", []),
            "confidence": result.get("confidence", "medium"),
        })

    return captions


def save_captions(captions: list[dict], output_path: str = None):
    if output_path is None:
        output_path = PROCESSED_DIR / "chunks" / "image_captions.jsonl"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        for item in captions:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[Captioner] Saved {len(captions)} captions → {output_path}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m rag.image_captioner <images_dir> [doc_id] [language]")
        print("Example: python -m rag.image_captioner data/processed/images/zh/材料科学基础_清华 材料科学基础_清华 zh")
        sys.exit(1)

    images_dir = sys.argv[1]
    doc_id = sys.argv[2] if len(sys.argv) > 2 else Path(images_dir).parent.name
    language = sys.argv[3] if len(sys.argv) > 3 else "zh"

    captions = caption_folder(images_dir, doc_id, language)
    save_captions(captions)
