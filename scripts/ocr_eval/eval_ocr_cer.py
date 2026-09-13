"""OCR 字符错误率(CER)评估脚本.

用法:
    cd backend
    .venv\\Scripts\\python ../scripts/ocr_eval/eval_ocr_cer.py

前置条件:
    1. 在 .env 中配置有效的 OCR_LLM_API_KEY(智谱 glm-4v-flash 或其他视觉模型)
    2. 将学生原图放入 scripts/ocr_eval/samples/ 目录(支持 .png/.jpg/.jpeg)
    3. 将人工逐字真值文本放入 scripts/ocr_eval/ground_truth/ 目录,
       文件名与图片同名(不含扩展名), 后缀 .txt, 例如:
         samples/student_01.png  ↔  ground_truth/student_01.txt

输出:
    - 逐张图片的识别文本、真值文本、CER
    - 汇总平均 CER、加权 CER(按字符数加权)
    - 结果写入 scripts/ocr_eval/cer_report.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# 让脚本能导入 backend.app 下的模块
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.parsers.image_ocr import ocr_image, OCRError, OCRConfigError  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
SAMPLES_DIR = EVAL_DIR / "samples"
GROUND_TRUTH_DIR = EVAL_DIR / "ground_truth"
REPORT_PATH = EVAL_DIR / "cer_report.json"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def levenshtein_distance(s1: str, s2: str) -> int:
    """计算两个字符串的编辑距离(Levenshtein distance)."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def compute_cer(reference: str, hypothesis: str) -> tuple[float, int, int, int, int]:
    """计算字符错误率 CER.

    CER = (S + D + I) / N
    返回 (cer, edit_dist, ref_len, hyp_len, operations)
    operations 为编辑距离(=S+D+I)
    """
    ref = reference.strip()
    hyp = hypothesis.strip()
    n = len(ref)
    if n == 0:
        return (0.0 if len(hyp) == 0 else 1.0, len(hyp), 0, len(hyp), len(hyp))
    dist = levenshtein_distance(ref, hyp)
    cer = dist / n
    return cer, dist, n, len(hyp), dist


def normalize_text(text: str) -> str:
    """简单归一化: 去除首尾空白、统一换行、合并多余空白."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def main() -> int:
    print("=" * 60)
    print("OCR CER 评估")
    print("=" * 60)

    if not SAMPLES_DIR.exists():
        print(f"[错误] 样本目录不存在: {SAMPLES_DIR}")
        return 1
    if not GROUND_TRUTH_DIR.exists():
        print(f"[错误] 真值目录不存在: {GROUND_TRUTH_DIR}")
        return 1

    image_files = sorted(
        p for p in SAMPLES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    if not image_files:
        print(f"[提示] 样本目录为空: {SAMPLES_DIR}")
        print("       请将学生原图放入该目录后重新运行。")
        return 0

    print(f"找到 {len(image_files)} 张样本图片\n")

    results = []
    total_dist = 0
    total_ref_chars = 0
    success = 0
    failed = 0

    for img_path in image_files:
        gt_path = GROUND_TRUTH_DIR / f"{img_path.stem}.txt"
        print(f"--- {img_path.name} ---")

        if not gt_path.exists():
            print(f"  [跳过] 缺少真值文件: {gt_path.name}")
            results.append({
                "image": img_path.name,
                "status": "skipped",
                "reason": "missing_ground_truth",
            })
            failed += 1
            continue

        reference = normalize_text(gt_path.read_text(encoding="utf-8"))

        try:
            t0 = time.time()
            hypothesis, provider = ocr_image(img_path)
            elapsed = time.time() - t0
            hypothesis = normalize_text(hypothesis)
        except (OCRError, OCRConfigError) as e:
            print(f"  [失败] OCR 调用失败: {e}")
            results.append({
                "image": img_path.name,
                "status": "failed",
                "reason": str(e),
                "ground_truth": reference,
            })
            failed += 1
            continue

        cer, dist, ref_len, hyp_len, _ = compute_cer(reference, hypothesis)
        total_dist += dist
        total_ref_chars += ref_len
        success += 1

        print(f"  provider : {provider}")
        print(f"  耗时     : {elapsed:.2f}s")
        print(f"  真值字符数: {ref_len}  识别字符数: {hyp_len}")
        print(f"  编辑距离 : {dist}")
        print(f"  CER      : {cer:.4f} ({cer*100:.2f}%)")
        print(f"  真值     : {reference[:80]}{'...' if len(reference) > 80 else ''}")
        print(f"  识别     : {hypothesis[:80]}{'...' if len(hypothesis) > 80 else ''}")
        print()

        results.append({
            "image": img_path.name,
            "status": "ok",
            "provider": provider,
            "elapsed_sec": round(elapsed, 3),
            "cer": round(cer, 6),
            "edit_distance": dist,
            "ref_chars": ref_len,
            "hyp_chars": hyp_len,
            "ground_truth": reference,
            "hypothesis": hypothesis,
        })

    # 汇总
    weighted_cer = total_dist / total_ref_chars if total_ref_chars > 0 else 0.0
    avg_cer = (
        sum(r["cer"] for r in results if r["status"] == "ok") / success
        if success > 0 else 0.0
    )

    summary = {
        "total_samples": len(image_files),
        "success": success,
        "failed": failed,
        "average_cer": round(avg_cer, 6),
        "weighted_cer": round(weighted_cer, 6),
        "total_reference_chars": total_ref_chars,
        "total_edit_distance": total_dist,
        "results": results,
    }

    REPORT_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 60)
    print("汇总")
    print("=" * 60)
    print(f"样本总数 : {len(image_files)}")
    print(f"成功     : {success}")
    print(f"失败     : {failed}")
    print(f"平均 CER : {avg_cer:.4f} ({avg_cer*100:.2f}%)")
    print(f"加权 CER : {weighted_cer:.4f} ({weighted_cer*100:.2f}%)  [按真值字符数加权]")
    print(f"报告已写入: {REPORT_PATH}")
    print()

    if failed > 0:
        print("[注意] 有失败样本, 请检查 OCR API Key 是否有效、网络是否通畅。")
        print("       智谱 Key 过期会返回 HTTP 401, 更新 .env 中 OCR_LLM_API_KEY 后重跑。")

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
