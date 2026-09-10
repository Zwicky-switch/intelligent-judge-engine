"""实操视频评测 —— 基础版(音轨转写内容判分 + 不可判步骤转人工).

基础版采用"简单逻辑":
1. 上传视频由 faster-whisper 直接转写音轨(PyAV 解码, 零额外依赖), 得到转写文本与词级时间戳;
2. 对量规中**配置了 keywords** 的步骤: 复用主观题判点器(_judge_point), 按转写文本命中判
   满足/部分/不满足 并给分;
3. 对**未配置 keywords** 的步骤(如姿态/动作/时序类): 标记 evidence='insufficient'(证据不足),
   不推断学生未完成、不扣分, 整卷进入人工复核, 由教师按步骤清单补齐评定;
4. 无转写文本(如静音视频/ASR 失败): 保持"证据不足转人工", 不自动给 0 分。

注意: 本版未接入姿态估计/动作识别/时序对齐, 属"音轨内容覆盖"维度的自动判分,
动作类步骤的最终分以教师人工评定为准(强制复核兜底)。
"""
from __future__ import annotations

import logging

from app.constants import (
    V_SATISFIED, V_PARTIAL, V_UNSATISFIED, LVL_SAMPLE, LVL_FORCED,
)
from app.engines.base import EngineOutcome, EvidenceHit, PointResult, clamp_score
from app.engines.subjective import _judge_point
from app.parsers.text import normalize_answer_text

logger = logging.getLogger(__name__)


def grade_video(item: dict, content: str = "", segments: list | None = None) -> EngineOutcome:
    max_score = float(item.get("max_score", 10.0))
    rubric = item.get("rubric") or []
    text = normalize_answer_text(content or "")
    outcome = EngineOutcome(max_score=max_score)

    if not text:
        # 无转写文本(静音/ASR 未出字): 证据不足, 转人工, 不自动给 0
        outcome.total = 0.0
        outcome.point_results = []
        outcome.hits = [
            EvidenceHit(point_id=s.get("step_id") or f"S{i + 1}", label="insufficient",
                        kind="video_action", source_type="video", confidence=0.0,
                        note=f"步骤「{s.get('description', '')}」无音轨转写证据, 需人工按视频评定")
            for i, s in enumerate(rubric)
        ]
        outcome.review_level = LVL_FORCED
        outcome.confidence = 0.3
        outcome.reasoning = "视频无有效音轨转写文本, 基础版无法自动判分, 已转人工按步骤清单评定。"
        outcome.comment = "由教师依据视频与步骤清单人工评定。"
        outcome.extra = {"phase": "base", "steps": [
            {"step_id": s.get("step_id") or f"S{i + 1}", "status": "insufficient"}
            for i, s in enumerate(rubric)]}
        return outcome

    judged: list[dict] = []
    hits: list[EvidenceHit] = []
    insufficient: list[str] = []
    earned = 0.0
    point_total = 0.0
    for i, step in enumerate(rubric):
        sid = step.get("step_id") or step.get("point_id") or f"S{i + 1}"
        keywords = step.get("keywords") or []
        if not keywords:
            # 无关键词可召回(动作/时序类): 证据不足, 不扣分, 转人工
            insufficient.append(sid)
            hits.append(EvidenceHit(point_id=sid, label="insufficient",
                                    kind="video_action", source_type="video",
                                    confidence=0.0,
                                    note=f"步骤「{step.get('description', '')}」需动作/时序识别, 当前证据不足, 转人工评定"))
            continue
        j = _judge_point(step, text, i)
        j["point_id"] = sid
        judged.append(j)
        point_total += float(step.get("score", 0))
        if j["verdict"] == V_SATISFIED:
            earned += float(step.get("score", 0))
        elif j["verdict"] == V_PARTIAL:
            earned += 0.5 * float(step.get("score", 0))
        # unsatisfied: 未命中, 0 分(有转写文本仍完全未提及该步骤, 属合理扣分)
        if j["verdict"] in (V_SATISFIED, V_PARTIAL, V_UNSATISFIED):
            hits.append(EvidenceHit(
                point_id=sid, label="evidence", kind="video_content",
                source_type="video", snippet=text[:80], confidence=0.75,
                note=j["reason"]))

    # 总分: 只按"可自动判分"的步骤算(insufficient 点不参与, 避免不公平扣分),
    # 存在 insufficient 点 -> 强制人工复核补齐
    if point_total > 0:
        total = max_score * earned / point_total
    else:
        total = 0.0
    total = clamp_score(total, 0.0, max_score)
    has_insufficient = bool(insufficient)
    any_unknown = any(j["verdict"] == "unknown" for j in judged)

    outcome.total = total
    outcome.point_results = [PointResult(
        point_id=j["point_id"], description=j["description"],
        max=float(j["score"]), status=j["verdict"], earned=(
            float(j["score"]) if j["verdict"] == V_SATISFIED
            else 0.5 * float(j["score"]) if j["verdict"] == V_PARTIAL else 0.0),
        reason=j["reason"], confidence=j["confidence"]) for j in judged]
    outcome.hits = hits
    # 无动作/时序校验, 高分可能仅来自"口述步骤", 故不做 LVL_NONE 自动放行, 至少抽样复核
    outcome.review_level = LVL_FORCED if (has_insufficient or any_unknown) else LVL_SAMPLE
    outcome.confidence = round(0.55 + 0.1 * (len(judged) / max(len(rubric), 1)), 3)
    outcome.confidence = min(outcome.confidence, 0.85)
    outcome.reasoning = (
        f"基础版按音轨转写内容自动判 {len(judged)} 个可判步骤; "
        + (f"{len(insufficient)} 个动作/时序步骤证据不足已转人工评定。" if has_insufficient
           else "全部步骤可自动判分, 未发现证据不足项。"))
    outcome.comment = (
        "部分步骤需动作/时序识别, 已转教师按视频补齐评定。"
        if has_insufficient else "音轨转写内容覆盖了全部可判步骤, 建议教师抽样复核。")
    outcome.extra = {"phase": "base", "modality": "video", "steps": [
        {"step_id": s.get("step_id") or f"S{i + 1}", "status": (
            "insufficient" if s.get("step_id") in insufficient
            else next((j["verdict"] for j in judged if j["point_id"] == (s.get("step_id") or f"S{i + 1}")), "unknown"))
         } for i, s in enumerate(rubric)]}
    return outcome
