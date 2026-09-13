"""批量 ASR 转写: 对指定目录下音频调用 faster-whisper, 保存转写文本.

用法:
    cd backend
    .venv\\Scripts\\python ..\\scripts\\asr_eval\\batch_asr.py <音频目录>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.parsers.audio import get_asr  # noqa: E402

AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac", ".mp4"}


def main():
    if len(sys.argv) < 2:
        print("用法: batch_asr.py <音频目录>")
        return 1
    src_dir = Path(sys.argv[1])
    if not src_dir.exists():
        print(f"目录不存在: {src_dir}")
        return 1

    files = sorted(p for p in src_dir.rglob("*")
                   if p.is_file() and p.suffix.lower() in AUDIO_EXTS
                   and "_asr_out" not in p.parts)
    if not files:
        print(f"目录下没有音频文件: {src_dir}")
        return 1

    adapter = get_asr()
    if adapter is None:
        print("ASR 不可用(未安装 faster-whisper)")
        return 1

    out_dir = src_dir / "_asr_out"
    out_dir.mkdir(exist_ok=True)
    print(f"发现 {len(files)} 个音频文件\n")

    report = {}
    for p in files:
        print(f"--- {p.name} ---")
        try:
            transcript, segments, src = adapter.transcribe(p)
        except Exception as e:  # noqa: BLE001
            print(f"  [FAIL] {e}")
            report[p.stem] = {"status": "error", "error": str(e)}
            continue
        transcript = (transcript or "").strip()
        dur_ms = segments[-1]["end"] if segments else 0
        print(f"  转写 {len(transcript)} 字, 时长 ~{dur_ms/1000:.1f}s")
        print(f"  文本: {transcript[:120]}{'...' if len(transcript) > 120 else ''}")
        report[p.stem] = {"status": "ok", "src": src, "text": transcript,
                          "chars": len(transcript), "duration_ms": dur_ms,
                          "n_segments": len(segments)}
        (out_dir / f"{p.stem}.txt").write_text(transcript, encoding="utf-8")
        print()

    (out_dir / "asr_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已写入: {out_dir / 'asr_report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
