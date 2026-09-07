"""评阅提示词模板(量规约束).

原则: 模型不拥有"改分权", 只输出得分点判定类别 + 证据 + 评语 + 罚分建议;
最终分值由引擎按量规权重重算, 并对模型输出二次裁剪(见 subjective 引擎)。
"""
from __future__ import annotations

import json

_VERDICT_DESC = {
    "satisfied": "明确满足该得分点(有直接、正确的表述)",
    "partial": "部分满足(要点相关但表述不完整/含小错/缺关键前提)",
    "unsatisfied": "不满足(缺失或答非所问/概念错误)",
    "unknown": "无法判断(作答信息不足以判定, 如指图/超纲写法)——此状态会强制转人工复核",
}

SCORE_SYSTEM = (
    "你是高校课程的主观题评阅助手, 采用『量规约束 + 证据优先』原则工作。\n"
    "硬性规则:\n"
    "1. 你无权直接给分。你只能对每个得分点判断其为满足/部分满足/不满足/无法判断四类之一, "
    "并给出作答原文中的证据(字符起止位置)与一句话理由。\n"
    "2. 证据必须来自学生作答原文, 字符位置基于我提供的『学生作答文本』逐字计数(含标点, 从 0 开始)。\n"
    "3. 只判断题面明确要求考查的得分点; 学生额外写对但与得分点无关的内容不额外加分。\n"
    "4. 只输出一个 JSON 对象, 不要输出任何解释文字。\n"
)


def _rubric_block(rubric: list) -> str:
    lines = []
    for p in rubric:
        lines.append(
            f'- {p.get("point_id")} [{p.get("score")} 分]: {p.get("description")}'
            + (f' (参考关键词: {", ".join(p.get("keywords") or [])})' if p.get("keywords") else "")
        )
    return "\n".join(lines)


def _field(item, name: str, default):
    """评分引擎/编排器传入的是 dict(item_engine_dict), 兼容 ORM Item 两种形态."""
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def subjective_user_prompt(item, answer_text: str) -> str:
    rubric = _field(item, "rubric", []) or []
    verdict_help = "\n".join(f'- {k}: {v}' for k, v in _VERDICT_DESC.items())
    payload = {
        "题干": _field(item, "title", "") or "",
        "评分量规(逐得分点满分, 引擎将据此重算分, 你只需给判定类别)": rubric,
        "参考答案": _field(item, "reference_answer", "") or "",
        "学生作答": answer_text,
    }
    user = (
        "请根据量规评判下列主观题作答。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=1)
        + "\n\n判定类别含义:\n" + verdict_help
        + "\n\n输出 JSON 结构(严格):\n"
        + json.dumps({
            "point_judgments": [
                {
                    "point_id": "得分点编号(必须取自已给量规)",
                    "verdict": "satisfied|partial|unsatisfied|unknown",
                    "evidence_start": 0,
                    "evidence_end": 0,
                    "evidence_text": "作答原文片段",
                    "reason": "一句话理由",
                }
            ],
            "penalties": [
                {"reason": "扣分原因(单位错误/概念矛盾等)", "deduct": 0.5}
            ],
            "comment": "面向学生的建议评语(中文, 60 字内)",
            "overall_confidence": 0.0,
        }, ensure_ascii=False)
    )
    return user


def spoken_user_prompt(item, transcript: str) -> str:
    """口语内容逻辑层: 判断是否覆盖量规要点."""
    rubric = _field(item, "rubric", []) or []
    user = (
        "下面是一段学生的口语作答转写, 请判断其是否覆盖量规各要点。\n"
        + json.dumps({"题干": _field(item, "title", "") or "", "量规要点": rubric,
                      "转写": transcript}, ensure_ascii=False, indent=1)
        + "\n输出 JSON: {\"point_judgments\":[{...同上, 无证据位置时给出要点对应转写片段/关键词}], "
        "\"comment\":\"60字内\", \"overall_confidence\":0.0}"
    )
    return user
