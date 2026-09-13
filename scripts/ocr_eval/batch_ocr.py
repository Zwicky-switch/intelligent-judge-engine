"""批量 OCR: 对 samples/ 下所有图片调用智谱视觉模型, 保存识别文本到 results/.

用法:
    cd backend
    .venv\\Scripts\\python ..\\scripts\\ocr_eval\\batch_ocr.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.parsers.image_ocr import OCRError, ocr_image  # noqa: E402

HERE = Path(__file__).parent
SAMPLES = HERE / "samples"
RESULTS = HERE / "results"


def main():
    RESULTS.mkdir(exist_ok=True)
    imgs = sorted(SAMPLES.glob("*"))
    imgs = [p for p in imgs if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}]
    if not imgs:
        print("samples/ 下没有图片")
        return

    print(f"发现 {len(imgs)} 张图片:\n")
    report = {}
    for p in imgs:
        print(f"--- {p.name} ---")
        try:
            text, provider = ocr_image(p)
        except OCRError as e:
            print(f"  [FAIL] {e}")
            report[p.stem] = {"status": "error", "error": str(e)}
            continue
        print(f"  provider={provider}, 识别 {len(text)} 字")
        report[p.stem] = {"status": "ok", "provider": provider, "text": text,
                          "chars": len(text)}
        (RESULTS / f"{p.stem}.txt").write_text(text, encoding="utf-8")
        print()

    (RESULTS / "ocr_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已写入: {RESULTS / 'ocr_report.json'}")


if __name__ == "__main__":
    main()
