"""音频/口语答案接入: 质量检查 + ASR 适配器接口.

ASR 为可替换插件:
- 安装了 faster-whisper(可选依赖) -> WhisperASR(词级时间戳);
- 未安装/离线 -> 需人工誊抄侧车文本, 否则发音层标记"无数据"(不硬编分)。
"""
from __future__ import annotations

import logging
import wave
from pathlib import Path

logger = logging.getLogger(__name__)

ALLOWED_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".webm"}


def wav_duration_ms(path: Path) -> int | None:
    """wav 文件时长(ms); 非 wav 或无 wave 支持返回 None."""
    try:
        with wave.open(str(path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            return int(frames / rate * 1000) if rate else None
    except Exception:
        return None


def basic_audio_check(path: Path) -> dict:
    """质量门控(音频): 格式/空文件/过短."""
    flags: list[str] = []
    notes: list[str] = []
    size = path.stat().st_size if path.exists() else 0
    if not path.exists() or size == 0:
        return {"pass": False, "quality_score": 0.0, "flags": ["empty"],
                "notes": ["音频文件为空或缺失"], "duration_ms": None}
    ext = path.suffix.lower()
    if ext not in ALLOWED_AUDIO_EXT:
        flags.append("format")
        notes.append(f"不支持的音频格式 {ext}")
    dur = wav_duration_ms(path) if ext == ".wav" else None
    if dur is not None and dur < 500:
        flags.append("too_short")
        notes.append("音频过短(<0.5s), 疑似空录音")
    score = 0.0 if flags else 1.0
    return {"pass": not flags, "quality_score": score, "flags": flags,
            "notes": notes, "duration_ms": dur}


class ASRAdapter:
    """ASR 插件基类. 子类实现 transcribe -> (text, segments)."""

    available = False

    def transcribe(self, path: Path) -> tuple[str, list, str]:
        raise NotImplementedError


class ManualTranscriptASR(ASRAdapter):
    """人工誊抄文本(无真实 ASR 时的可靠证据来源), 附带说明无词级对齐."""

    available = True

    def __init__(self, transcript: str):
        self.transcript = transcript

    def transcribe(self, path: Path) -> tuple[str, list, str]:
        return self.transcript, [], "manual"


def get_asr(manual_transcript: str = "") -> ASRAdapter | None:
    """返回可用 ASR; 有 manual 文本优先用人工; 否则检测 faster-whisper."""
    if manual_transcript and manual_transcript.strip():
        return ManualTranscriptASR(manual_transcript.strip())
    try:
        from faster_whisper import WhisperModel  # noqa: F401
        return _WhisperASR()
    except Exception:
        return None


class _WhisperASR(ASRAdapter):
    """faster-whisper 可选接入(词级时间戳). 需自行 pip install faster-whisper."""

    available = True

    def __init__(self, model_size: str = "small"):
        from faster_whisper import WhisperModel

        self._model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe(self, path: Path) -> tuple[str, list, str]:
        segs, _info = self._model.transcribe(str(path), word_timestamps=True)
        segments = []
        text = ""
        for seg in segs:
            text += (seg.text or "") + ""
            words = []
            for w in (seg.words or []):
                words.append({"word": w.word, "start": int(w.start * 1000),
                              "end": int(w.end * 1000)})
            segments.append({"text": seg.text or "", "start": int(seg.start * 1000),
                             "end": int(seg.end * 1000), "words": words})
        return text.strip(), segments, "whisper"
