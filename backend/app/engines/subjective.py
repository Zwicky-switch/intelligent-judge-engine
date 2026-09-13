"""文本主观题智能评阅引擎(量规约束 + 证据检索 + 小模型判别 + 大模型解释).

处理:
1. 把量规拆为得分点卡片;
2. 关键词召回答案片段 -> 判 满足/部分/不满足/无法判断;
3. 引擎按量规权重算分(大模型不直接给分);
4. 若有配置国产大模型: 让它复核判定类别、给出罚分建议与评语(仍会被量规二次约束);
5. 输出证据(字符区间)与置信度 -> 由编排器落库并路由复核。
"""
from __future__ import annotations

import logging
import re

from app.config import settings
from app.engines.base import EngineOutcome, EvidenceHit, PointResult, clamp_score
from app.constants import (
    V_SATISFIED, V_PARTIAL, V_UNSATISFIED, V_UNKNOWN,
    LVL_NONE, LVL_SAMPLE, LVL_FORCED,
)
from app.llm.json_llm import request_json
from app.llm.prompts import SCORE_SYSTEM, subjective_user_prompt
from app.parsers.text import coverage_ratio, slot_coverage_ratio, quality_gate_text

logger = logging.getLogger(__name__)

# 疑似"引图作答"导致的无法判断
_REF_FIGURE_RE = re.compile(r"(如图|见上?图|参见图|详见附图|上图中|如图所示)")


def _clamp_span(start, end, limit: int):
    start = max(0, min(int(start), limit))
    end = max(start, min(int(end), limit))
    return start, end


def _verdict_from_ratio(ratio: float, desc: str, matched: set[str] | None = None) -> tuple[str, str]:
    if ratio >= 0.8:
        return V_SATISFIED, f"覆盖得分点要点(覆盖率 {ratio:.0%})"
    # 命中过关键词但覆盖率未达阈值的作答, 按教学直觉给部分分, 而非 0 分
    if ratio >= 0.4 or (matched and ratio > 0):
        return V_PARTIAL, f"部分覆盖得分点要点(覆盖率 {ratio:.0%}), 表述/前提不完整"
    return V_UNSATISFIED, f"未覆盖得分点({desc})"


def _judge_point(point: dict, text: str, idx: int) -> dict:
    """本地确定性判点(小模型判别层).

    支持两种量规结构:
    - 传统: point.keywords = [字符串...], 按字符串面覆盖率判点
    - 语义槽(评分算法优化 v2): point.slots = [{label, keywords:[变体...]}...],
      按"命中槽数/总槽数"判点, 槽内任一变体命中即覆盖, 消除同义变体膨胀分母缺陷
    """
    keywords = point.get("keywords") or []
    slots = point.get("slots") or []
    point_id = point.get("point_id") or f"P{idx + 1}"
    score = float(point.get("score", 0))
    desc = point.get("description") or ""

    if slots:
        ratio, hits, matched = slot_coverage_ratio(text, slots)
    else:
        ratio, hits, matched = coverage_ratio(text, keywords)
    verdict, reason = _verdict_from_ratio(ratio, desc, matched)

    # 无法判断: 疑似引图作答/超纲符号, 证据不足不推断学生不会
    if _REF_FIGURE_RE.search(text) and (keywords or slots):
        verdict = V_UNKNOWN
        reason = "作答疑似引用题目附图/外部图, 文本证据不足, 需人工复核"

    if slots:
        miss_labels = [
            s.get("label") for s in slots
            if not any(kw in text for kw in (s.get("keywords") or []))
        ]
        if miss_labels and verdict in (V_SATISFIED, V_PARTIAL):
            reason += " | 未覆盖: " + "、".join(miss_labels[:5])
    else:
        missing = [k for k in (keywords or []) if k not in matched]
        if missing and verdict in (V_SATISFIED, V_PARTIAL):
            reason += " | 未命中: " + "、".join(missing[:5])

    return {
        "point_id": point_id, "description": desc,
        "score": score, "verdict": verdict, "reason": reason,
        "hits": hits, "ratio": ratio, "keywords": keywords,
        "confidence": 0.9 if verdict == V_SATISFIED else (0.55 if verdict == V_PARTIAL
                                                          else (0.85 if verdict == V_UNSATISFIED else 0.25)),
    }


def _llm_judge_points(item: dict, text: str, _local: list[dict], llm) -> dict | None:
    """大模型解释/复核层(可选). 失败或无法解析返回 None(不阻断, 但记录原因)."""
    try:
        resp = request_json(llm, SCORE_SYSTEM, subjective_user_prompt(item, text))
    except Exception as e:  # noqa: BLE001
        logger.warning("主观题大模型复核失败(item=%s): %s; 使用本地判点", item.get("title"), e)
        return None
    if not isinstance(resp, dict):
        logger.warning("主观题大模型响应非对象, 丢弃: %s", str(resp)[:200])
        return None
    return resp


def grade_subjective(item: dict, answer_text: str, llm=None,
                     quality: dict | None = None) -> EngineOutcome:
    rubric = item.get("rubric") or []
    max_score = float(item.get("max_score", 10.0))
    text = answer_text or ""
    # 入库 quality 应即质量门控结果(含 pass); 若只有 {quality_score,flags,notes} 这类
    # 旧/外围结构, 则以当前文本重新门控, 保证不越权跳过人工路由
    q = quality if (quality and "pass" in quality) else quality_gate_text(text, item_type="subjective_text")
    outcome = EngineOutcome(max_score=max_score)

    if not q["pass"] or not text:
        note = "; ".join(q["notes"]) or "空白作答"
        outcome.total = 0.0
        outcome.confidence = 0.5
        outcome.reasoning = f"质量门控未通过({note}); 未自动给 0 分, 转人工复核"
        outcome.review_level = LVL_FORCED
        outcome.extra["quality"] = q
        outcome.point_results = [PointResult(
            point_id="gate", description="质量门控", max=max_score,
            status=V_UNSATISFIED, earned=0.0, reason=outcome.reasoning)]
        return outcome

    # 1) 本地判点
    local = [_judge_point(p, text, i) for i, p in enumerate(rubric)]

    # 2) 大模型复核(仅当 rubric 有内容且 llm 可用)
    llm_resp = _llm_judge_points(item, text, local, llm) if (llm and rubric) else None
    if llm_resp:
        # 合并: 模型对点判定置信度高时才采纳其判定类别(仍映射回量规权重)
        by_id = {p.get("point_id"): p for p in local}
        for j in (llm_resp.get("point_judgments") or []):
            pid = j.get("point_id")
            if pid in by_id and j.get("verdict") in (V_SATISFIED, V_PARTIAL, V_UNSATISFIED, V_UNKNOWN):
                conf = float(j.get("confidence", 0.0) or 0.0)
                local_point = by_id[pid]
                if conf >= 0.7:
                    local_point["verdict"] = j["verdict"]
                    local_point["reason"] = f"模型复核: {j.get('reason','')}"
                elif conf >= 0.5 and j["verdict"] == V_PARTIAL and local_point["verdict"] == V_SATISFIED:
                    local_point["verdict"] = V_PARTIAL
                    local_point["reason"] = "模型复核认为仅部分满足"
                local_point["confidence"] = max(local_point["confidence"], conf)

    # 3) 量规权重算分(含部分 0.5, 罚分)
    point_results: list[PointResult] = []
    total = 0.0
    for lp in local:
        pscore = float(lp["score"])
        if lp["verdict"] == V_SATISFIED:
            earned = pscore
        elif lp["verdict"] == V_PARTIAL:
            earned = pscore * 0.5
        else:
            earned = 0.0
        total += earned
        point_results.append(PointResult(
            point_id=lp["point_id"], description=lp["description"],
            max=pscore, status=lp["verdict"], earned=round(earned, 2),
            reason=lp["reason"], confidence=lp["confidence"]))

    # 罚分(仅采纳 item.scoring_policy 显式配置的罚项; 模型建议必须落在其 max 内)
    penalties: list[dict] = []
    policy_penalties = (item.get("scoring_policy") or {}).get("penalties") or []
    pen_map = {p.get("reason"): float(p.get("max", 0)) for p in policy_penalties}
    suggested = (llm_resp or {}).get("penalties") or []
    for sp in suggested:
        reason = (sp or {}).get("reason", "")
        if reason in pen_map:
            deduct = min(float(sp.get("deduct", 0) or 0), pen_map[reason])
            if deduct > 0:
                penalties.append({"reason": reason, "deduct": deduct})
                total -= deduct

    total = clamp_score(total, 0.0, max_score)

    # 4) 置信度与复核路由
    confs = [p.confidence for p in point_results] or [0.9]
    confidence = round(sum(confs) / len(confs), 3)
    if llm_resp and isinstance(llm_resp.get("overall_confidence"), (int, float)):
        llm_conf = float(llm_resp["overall_confidence"])
        confidence = round(0.5 * confidence + 0.5 * llm_conf, 3)

    any_unknown = any(p.status == V_UNKNOWN for p in point_results)
    threshold = float((item.get("scoring_policy") or {}).get("review_threshold")
                      or settings.REVIEW_THRESHOLD)
    auto_threshold = float((item.get("scoring_policy") or {}).get("auto_threshold", 0.93))
    auto_release = bool((item.get("scoring_policy") or {}).get("auto_release", False))
    if any_unknown or confidence < threshold:
        review_level = LVL_FORCED
    elif auto_release and confidence >= auto_threshold and not any_unknown:
        review_level = LVL_NONE
    else:
        review_level = LVL_SAMPLE

    comment = (llm_resp or {}).get("comment") or _default_comment(point_results, total, max_score)

    # 5) 证据
    hits: list[EvidenceHit] = []
    for lp in local:
        for h in lp.get("hits", [])[:3]:
            s, e = h["start"], h["end"]
            hits.append(EvidenceHit(
                point_id=lp["point_id"], label=lp["verdict"], kind="keyword",
                source_type="text", ref_start=s, ref_end=e,
                snippet=text[s:e], confidence=lp["confidence"]))
        if not lp.get("hits"):
            hits.append(EvidenceHit(
                point_id=lp["point_id"], label=lp["verdict"], kind="no_evidence",
                source_type="text", ref_start=None, ref_end=None,
                snippet="", confidence=lp["confidence"],
                note=lp["reason"]))

    outcome.total = total
    outcome.point_results = point_results
    outcome.penalties = penalties
    outcome.hits = hits
    outcome.comment = comment
    outcome.reasoning = f"逐得分点评阅完成, 未满足/部分满足项见得分点明细"
    outcome.confidence = confidence
    outcome.review_level = review_level
    outcome.extra["quality"] = q
    return outcome


def _default_comment(point_results: list[PointResult], total: float, max_score: float) -> str:
    sat = sum(1 for p in point_results if p.status == V_SATISFIED)
    partial = sum(1 for p in point_results if p.status in (V_PARTIAL, V_UNKNOWN))
    if sat == len(point_results) and point_results:
        return "作答覆盖了全部得分点, 表述规范, 建议保持。"
    if total >= max_score * 0.7:
        return "整体较好, 少数得分点表述不够完整, 请补全关键步骤与前提。"
    if total >= max_score * 0.4:
        return "覆盖了部分得分点, 建议加强概念表述与推理过程。"
    return "要点覆盖不足, 建议对照参考答案逐点自查后重练。"
