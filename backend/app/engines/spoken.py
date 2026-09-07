"""口语评测引擎: 可解释四层指标(发音/流畅/表达/内容逻辑).

- 内容逻辑: 量规要点覆盖 + 因果/结构提示(可 LLM 复核);
- 语言表达: 术语命中 + 词汇/句法启发式;
- 语流流畅: 依赖词级时间戳(有 ASR/侧车时间时计算), 否则标注"无数据";
- 发音准确: 需音素级 ASR/强制对齐, 未接入时标注"无数据" —— 不硬编分。

无数据的维度不参与总分(不做不公平扣分), 但会在报告/教师端如实提示待接入。
口语默认需教师抽样复核。
"""
from __future__ import annotations

import logging
import re

from app.engines.base import EngineOutcome, EvidenceHit, clamp_score
from app.engines.subjective import _judge_point, _REF_FIGURE_RE
from app.constants import (
    LAYER_PRON, LAYER_FLUENCY, LAYER_EXPRESSION, LAYER_CONTENT,
    SPOKEN_LAYERS, V_UNKNOWN, LVL_SAMPLE, LVL_FORCED,
)
from app.llm.json_llm import request_json
from app.llm.prompts import SCORE_SYSTEM, spoken_user_prompt
from app.parsers.text import normalize_answer_text

logger = logging.getLogger(__name__)

_DEFAULT_WEIGHTS = {LAYER_PRON: 0.25, LAYER_FLUENCY: 0.25,
                    LAYER_EXPRESSION: 0.25, LAYER_CONTENT: 0.25}


def _content_layer(item: dict, text: str, llm) -> tuple[float, str, list, list]:
    """内容逻辑层: 逐量规要点判点, 平均覆盖."""
    rubric = item.get("rubric") or []
    if not rubric:
        return 0.0, "未配置内容要点量规", [], []
    judged = [_judge_point(p, text, i) for i, p in enumerate(rubric)]
    # 可选 LLM 复核
    if llm:
        try:
            resp = request_json(llm, SCORE_SYSTEM, spoken_user_prompt(item, text))
            ov = float((resp or {}).get("overall_confidence", 0) or 0)
            if ov >= 0.7:
                js = (resp or {}).get("point_judgments") or []
                by_id = {j.get("point_id"): j for j in judged}
                for j in js:
                    pid = j.get("point_id")
                    if pid in by_id and j.get("verdict") in ("satisfied", "partial", "unsatisfied", "unknown"):
                        by_id[pid]["verdict"] = j["verdict"]
                        by_id[pid]["reason"] = "模型复核: " + (j.get("reason") or "")
        except Exception as e:  # noqa: BLE001
            logger.warning("口语内容层大模型复核失败: %s; 使用本地判点", e)
    vals = []
    for j in judged:
        vals.append({"point_id": j["point_id"], "verdict": j["verdict"],
                     "reason": j["reason"], "ratio": j["ratio"]})
    # 覆盖得分(满足=1, 部分=0.5)
    ratio = sum(1 if v["verdict"] == "satisfied" else 0.5 if v["verdict"] == "partial"
                else 0.0 for v in vals) / max(len(vals), 1)
    detail = "；".join(f"{v['point_id']}:{v['verdict']}" for v in vals) or "无要点"
    unknown = any(v["verdict"] == V_UNKNOWN for v in vals)
    return clamp_score(ratio), detail, vals, ([V_UNKNOWN] if unknown else [])


def _expression_layer(item: dict, text: str) -> tuple[float, str]:
    """语言表达: 术语命中率 + 表达长度/结构启发式."""
    text = text or ""
    term_bank = (item.get("answer_config") or {}).get("term_bank") or []
    term_hit = 0.0
    if term_bank:
        hit = sum(1 for t in term_bank if t and t in text)
        term_hit = hit / len(term_bank)
    n = len(text)
    length_score = min(1.0, n / 80.0)
    # 结构提示(有连接词/分点)
    structure = 0.0
    if re.search(r"(首先|其次|然后|最后|因为|所以|因此|综上|第一|第二)", text):
        structure = 0.5
    if len(re.findall(r"[。！？!?]", text)) >= 2:
        structure = min(1.0, structure + 0.5)
    score = clamp_score(0.45 * term_hit + 0.35 * length_score + 0.2 * structure)
    note = (f"术语命中 {sum(1 for t in term_bank if t in text)}/{len(term_bank)}"
            if term_bank else "未配置术语库")
    return score, note


def _fluency_layer(text: str, segments: list) -> tuple[float | None, str]:
    """语流流畅: 词级时间戳计算语速与停顿; 无时间戳返回 None."""
    words: list = []
    for seg in segments or []:
        words.extend(seg.get("words") or [])
    if not words or not any(w.get("start") is not None for w in words):
        return None, "无词级时间戳(ASR 未接入), 无法计算"
    if len(words) < 2:
        return 0.5, "有效词过少"
    start = min(w["start"] for w in words)
    end = max(w["end"] for w in words)
    duration_s = max((end - start) / 1000.0, 0.5)
    wpm = len(words) / duration_s * 60.0
    # 停顿
    pauses = 0
    sorted_w = sorted(words, key=lambda w: w["start"])
    for a, b in zip(sorted_w, sorted_w[1:]):
        if (b["start"] - a["end"]) > 400:
            pauses += 1
    # 语速得分: 理想 ~120-180 wpm; 停顿惩罚
    rate_score = clamp_score(1.0 - abs(wpm - 150) / 180.0)
    pause_score = clamp_score(1.0 - pauses * 0.15)
    score = clamp_score(0.6 * rate_score + 0.4 * pause_score)
    note = f"语速约 {int(wpm)} 词/分钟, 检测停顿 {pauses} 处"
    return score, note


def grade_spoken(item: dict, transcript: str, segments: list | None = None,
                 llm=None, quality: dict | None = None) -> EngineOutcome:
    max_score = float(item.get("max_score", 10.0))
    text = normalize_answer_text(transcript or "")
    outcome = EngineOutcome(max_score=max_score)
    outcome.review_level = LVL_SAMPLE
    if not text:
        outcome.total = 0.0
        outcome.reasoning = "口语作答无转写文本(可能为空白录音), 转人工复核"
        outcome.review_level = LVL_FORCED
        outcome.extra["layers"] = {k: {"status": "nodata", "score": None} for k in SPOKEN_LAYERS}
        return outcome

    weights = dict((item.get("scoring_policy") or {}).get("spoken_weights") or _DEFAULT_WEIGHTS)
    layers = {}

    # 内容逻辑
    c_score, c_detail, c_vals, c_flags = _content_layer(item, text, llm)
    layers[LAYER_CONTENT] = {"status": "ok", "score": c_score, "detail": c_detail,
                             "unknown": bool(c_flags)}
    # 表达
    e_score, e_detail = _expression_layer(item, text)
    layers[LAYER_EXPRESSION] = {"status": "ok", "score": e_score, "detail": e_detail}
    # 流畅
    f_score, f_detail = _fluency_layer(text, segments or [])
    layers[LAYER_FLUENCY] = ({"status": "ok", "score": f_score, "detail": f_detail}
                             if f_score is not None else {"status": "nodata", "score": None, "detail": f_detail})
    # 发音: 需 ASR 强制对齐, 当前无插件 -> 无数据
    layers[LAYER_PRON] = {"status": "nodata", "score": None,
                          "detail": "音素级 ASR/强制对齐未接入(可安装 faster-whisper + 对齐模型后启用)"}

    computed = {k: v for k, v in layers.items() if v["status"] == "ok" and v.get("score") is not None}
    total_weight = sum(weights[k] for k in computed)
    if computed and total_weight > 0:
        total = max_score * sum(weights[k] * computed[k]["score"] for k in computed) / total_weight
    else:
        total = 0.0
    total = clamp_score(total, 0.0, max_score)

    any_unknown = layers[LAYER_CONTENT].get("unknown") or any(
        p.get("verdict") == V_UNKNOWN for p in c_vals)

    hits: list[EvidenceHit] = []
    for k, v in computed.items():
        snippet = text[:80] if k in (LAYER_CONTENT, LAYER_EXPRESSION) else ""
        hits.append(EvidenceHit(point_id=k, label="evidence", kind=k,
                                source_type="audio", snippet=snippet,
                                confidence=0.8 if k != LAYER_CONTENT else 0.7,
                                note=v["detail"]))

    confidence = round(0.6 + 0.1 * (len(computed) / len(SPOKEN_LAYERS)), 3)
    outcome.total = total
    outcome.point_results = []
    outcome.hits = hits
    outcome.comment = _spoken_comment(total, max_score)
    outcome.reasoning = "四层口语评测完成; 未接入维度已标注无数据, 不计入扣分"
    outcome.confidence = min(confidence, 0.92)
    outcome.review_level = LVL_FORCED if any_unknown else LVL_SAMPLE
    outcome.extra["layers"] = layers
    if quality:
        outcome.extra["quality"] = quality
    return outcome


def _spoken_comment(total: float, max_score: float) -> str:
    r = total / max_score if max_score else 0
    if r >= 0.85:
        return "发音清楚、要点完整、表达流畅, 继续保持。"
    if r >= 0.6:
        return "要点基本覆盖, 表达可再组织得更连贯, 注意术语规范。"
    return "建议围绕量规要点重新组织作答, 先讲结论再展开依据。"
