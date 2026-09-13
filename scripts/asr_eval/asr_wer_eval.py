"""ASR WER/CER 评估: faster-whisper-large-v3 交叉转写 → 人工校对真值 → 计算 small 错误率.

"AI 充当人力"方案:
1. 用 faster-whisper-large-v3(准确率显著高于 small) 转写全部音频, 作为"准真值参考"
2. 输出到 reference/ 目录, 由校对员(人/AI)基于题目语境修正同音字/术语后作为最终真值
3. 用 small 转写结果(已有) 与该真值对比, 计算 词级 WER 与 字符级 CER

用法:
    cd backend
    .venv\\Scripts\\python ..\\scripts\\asr_eval\\asr_wer_eval.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

import jieba  # noqa: E402
from app.parsers.audio import _WhisperASR  # noqa: E402

HERE = Path(__file__).parent
RESULT_DIR = HERE / "results"
REFERENCE_DIR = HERE / "reference"      # large-v3 转写(待校对)
TRUTH_DIR = HERE / "ground_truth"       # 校对后的真值

# 音频来源(真实学生作答素材, 与 batch_asr 一致)
AUDIO_SOURCES = [
    ("采访录音 1", Path(r"C:\Users\刘奕飞\Desktop\作答资料\同学1（70分\采访录音 1.mp3")),
    ("采访录音 2", Path(r"C:\Users\刘奕飞\Desktop\作答资料\同学1（70分\采访录音 2.mp3")),
    ("采访录音 3", Path(r"C:\Users\刘奕飞\Desktop\作答资料\同学2（90分）\采访录音 3.mp3")),
    ("采访录音 4", Path(r"C:\Users\刘奕飞\Desktop\作答资料\同学2（90分）\采访录音 4.mp3")),
    ("题5", Path(r"C:\Users\刘奕飞\Desktop\作答资料\题5.mp4")),
]

# 已知 small 转写结果(来自 batch_asr 已跑结果)
def load_small_transcripts() -> dict:
    report = json.loads((RESULT_DIR / "asr_report.json").read_text(encoding="utf-8"))
    return {k: v["text"] for k, v in report.items() if v.get("status") == "ok"}


def levenshtein_distance(s1: str, s2: str) -> int:
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


def compute_cer(reference: str, hypothesis: str) -> float:
    ref, hyp = reference.strip(), hypothesis.strip()
    n = len(ref)
    if n == 0:
        return 1.0 if hyp else 0.0
    return levenshtein_distance(ref, hyp) / n


def compute_wer(reference: str, hypothesis: str) -> float:
    """词级 WER: jieba 分词后按词序列计算编辑距离 / 参考词数."""
    ref_words = list(jieba.cut(reference.strip()))
    hyp_words = list(jieba.cut(hypothesis.strip()))
    n = len(ref_words)
    if n == 0:
        return 1.0 if hyp_words else 0.0
    dist = levenshtein_distance(ref_words, hyp_words)
    return dist / n


def main():
    small = load_small_transcripts()
    if not small:
        print("未找到 small 转写结果, 请先运行 batch_asr.py")
        return 1

    # 若真值已存在(人工/AI校对), 直接使用, 跳过 large-v3 下载
    TRUTH_DIR.mkdir(exist_ok=True)
    existing_truths = {p.stem: p.read_text(encoding="utf-8").strip()
                       for p in TRUTH_DIR.glob("*.txt")}
    if existing_truths:
        print(f"找到 {len(existing_truths)} 份人工校对真值, 跳过 large-v3 转写\n")
        reference_texts = existing_truths
    else:
        # 1. large-v3 交叉转写(首次运行自动下载模型~3GB)
        print("=" * 70)
        print("Step 1/3: faster-whisper-large-v3 交叉转写(首次运行自动下载模型~3GB)")
        print("=" * 70)
        adapter = _WhisperASR(model_size="large-v3")
        if adapter is None:
            print("[错误] ASR 不可用")
            return 1

        REFERENCE_DIR.mkdir(exist_ok=True)
        reference_texts = {}
        for key, path in AUDIO_SOURCES:
            if not path.exists():
                print(f"  跳过(文件不存在): {key} ({path.name})")
                continue
            print(f"  转写 {key} ({path.name}) ...")
            try:
                transcript, segments, src = adapter.transcribe(path)
            except Exception as e:  # noqa: BLE001
                print(f"    [FAIL] {e}")
                continue
            transcript = (transcript or "").strip()
            reference_texts[key] = transcript
            (REFERENCE_DIR / f"{key}.txt").write_text(transcript, encoding="utf-8")
            print(f"    {len(transcript)} 字")
        print(f"  large-v3 转写已保存到: {REFERENCE_DIR}\n")

    # 2. 真值 = 人工校对版(已存在) 或 large-v3 原始
    truths = dict(existing_truths) if existing_truths else reference_texts

    # 3. 计算 WER/CER
    print("=" * 70)
    print("Step 2/3: WER/CER 计算(small vs 真值)")
    print("=" * 70)
    report = {}
    for key, ref in truths.items():
        hyp = small.get(key, "")
        if not hyp:
            print(f"  {key}: [无 small 转写]")
            continue
        cer = compute_cer(ref, hyp)
        wer = compute_wer(ref, hyp)
        print(f"  {key}: WER={wer:.2%}  CER={cer:.2%}  (ref {len(ref)}字 / hyp {len(hyp)}字)")
        report[key] = {
            "ref_source": "人工校对" if (TRUTH_DIR / f"{key}.txt").exists() else "large-v3(未校对)",
            "wer": round(wer, 6), "cer": round(cer, 6),
            "ref_chars": len(ref), "hyp_chars": len(hyp),
            "reference": ref, "hypothesis": hyp,
        }

    if report:
        avg_wer = sum(r["wer"] for r in report.values()) / len(report)
        avg_cer = sum(r["cer"] for r in report.values()) / len(report)
        print(f"\n  平均 WER={avg_wer:.2%}  平均 CER={avg_cer:.2%}  (n={len(report)})")
        summary = {"n": len(report), "avg_wer": round(avg_wer, 6),
                   "avg_cer": round(avg_cer, 6), "items": report}
        (RESULT_DIR / "asr_wer_cer_report.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  报告: {RESULT_DIR / 'asr_wer_cer_report.json'}")

    print("\n" + "=" * 70)
    print("Step 3/3: 人工校对真值(可选但推荐)")
    print("=" * 70)
    print("large-v3 转写已保存到 reference/, 请人工(或 AI 基于题目语境)")
    print("修正同音字/术语后覆盖到 ground_truth/ 同名 .txt, 再重跑本脚本。")
    print("示例修正: 侧力剂→测力计, 读书→读数, 调室→调试, 克度→刻度")
    return 0


if __name__ == "__main__":
    sys.exit(main())
