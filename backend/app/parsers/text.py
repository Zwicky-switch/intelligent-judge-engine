"""文本答案规范化、关键词召回与质量门控(方案 §4.2).

统一输出规范化的 content(即评分与证据定位都以它为准),
关键词命中返回在其中的字符区间 [start,end)。
"""
from __future__ import annotations

import re

_MAX_TEXT_LEN = 4000


def normalize_answer_text(s: str) -> str:
    """轻度规范化: 去首尾空白/折叠连续空白, 保留标点与段落."""
    text = str(s or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t　]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def find_spans(text: str, keywords: list[str]) -> list[dict]:
    """在 text 中召回关键词(短语)命中区间; 重叠命中只保留首个, 结果升序且不重叠.

    返回 [{'start','end','snippet','keyword'}]
    """
    spans: list[dict] = []
    for kw in (keywords or []):
        kw = str(kw).strip()
        if not kw:
            continue
        # 简单策略: 找首次出现
        pos = text.find(kw)
        if pos >= 0:
            spans.append({
                "start": pos, "end": pos + len(kw),
                "snippet": text[pos:pos + len(kw)], "keyword": kw,
            })
    # 去重重叠(同一位置附近多关键词)
    spans.sort(key=lambda x: (x["start"], -(x["end"] - x["start"])))
    merged: list[dict] = []
    for sp in spans:
        if merged and sp["start"] < merged[-1]["end"]:
            # 与上一命中重叠: 保留覆盖面更大的那个
            prev = merged[-1]
            if (sp["end"] - sp["start"]) > (prev["end"] - prev["start"]):
                merged[-1] = sp
            continue
        merged.append(sp)
    return merged


def coverage_ratio(text: str, keywords: list[str]) -> tuple[float, list[dict], set[str]]:
    """关键词覆盖度. 返回 (覆盖比例0-1, 命中区间, 命中集合).

    比例 = 命中去重字符数 / (该点关键词模板总长, 以各关键词字符长度加权估算)
    """
    hits = find_spans(text, keywords)
    covered_len = sum(e - s for s, e in [(h["start"], h["end"]) for h in hits])
    total_len = sum(len(str(k)) for k in (keywords or []) if str(k).strip())
    ratio = (covered_len / total_len) if total_len else 0.0
    matched = {h["keyword"] for h in hits}
    return min(ratio, 1.0), hits, matched


def quality_gate_text(text: str, *, item_type: str | None = None) -> dict:
    """质量门控: 空/过短/过长 -> 拒评转人工, 不静默判零.

    返回 {pass, quality_score(0-1), flags[], notes}
    """
    content = normalize_answer_text(text)
    flags: list[str] = []
    notes: list[str] = []
    score = 1.0
    if not content:
        flags.append("empty")
        notes.append("空白作答, 无内容可评")
        score = 0.0
    else:
        n = len(content)
        if n > _MAX_TEXT_LEN:
            flags.append("too_long")
            notes.append(f"作答过长({n}字符), 已截断风险, 转人工复核")
            score = min(score, 0.5)
        if n < 4 and (item_type == "subjective_text"):
            flags.append("too_short")
            notes.append("作答过短, 信息量不足")
            score = min(score, 0.6)
    return {"pass": not flags, "quality_score": round(score, 2),
            "flags": flags, "notes": notes}
