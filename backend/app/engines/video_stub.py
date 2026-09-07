"""实操视频评测 —— 阶段 2 占位实现.

按方案 §4.6: 视频评测只对量规明确配置的"步骤/关键动作/结果/安全"负责;
当前未接入姿态估计/动作识别/时序对齐, 因此:
- 每个步骤标记 evidence='insufficient'(证据不足), 不推断学生未完成, 不自动扣分;
- 整卷转人工按证据评定, 进入强制复核队列。
"""
from __future__ import annotations

from app.constants import LVL_FORCED
from app.engines.base import EngineOutcome, EvidenceHit


def grade_video(item: dict, content: str = "", segments: list | None = None) -> EngineOutcome:
    max_score = float(item.get("max_score", 10.0))
    rubric = item.get("rubric") or []
    hits: list[EvidenceHit] = []
    notes = []
    for i, step in enumerate(rubric):
        sid = step.get("step_id") or step.get("point_id") or f"S{i + 1}"
        hits.append(EvidenceHit(point_id=sid, label="insufficient",
                                kind="video_action", source_type="video",
                                confidence=0.0,
                                note=f"步骤「{step.get('description','')}」需视频动作/时序识别, 当前阶段证据不足"))
    outcome = EngineOutcome(max_score=max_score)
    outcome.total = 0.0
    outcome.point_results = []
    outcome.hits = hits
    outcome.review_level = LVL_FORCED
    outcome.confidence = 0.3
    outcome.reasoning = (
        "实操视频评测属方案第二阶段范围: 需接入姿态估计、物体/工具检测与步骤时序对齐后启用。"
        "当前不自动给 0 分, 已按证据不足转人工按步骤清单评定。"
    )
    outcome.comment = "由教师依据视频与步骤清单人工评定(当前无动作识别证据)。"
    outcome.extra = {"phase": 2, "steps": [{"step_id": s.get("step_id") or f"S{i + 1}",
                                            "status": "insufficient"} for i, s in enumerate(rubric)]}
    return outcome
