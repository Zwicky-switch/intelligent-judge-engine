"""评阅引擎公共数据结构.

一个 EngineOutcome 代表"一道答卷的一次评阅产出":
分数 + 得分点明细 + 证据 + 置信度 + 建议复核档位。
引擎只做纯计算并返回结构, 由 orchestrator 落库到 Score / Evidence。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.constants import LVL_NONE


@dataclass
class EvidenceHit:
    """一条证据(供 orchestrator 落 Evidence 表)."""
    point_id: str = ""
    label: str = "evidence"          # verdict 或 penalty / evidence
    kind: str = ""                   # keyword/semantic/diagram/...
    source_type: str = "text"        # text/audio/video
    ref_start: float | None = None   # 字符区间或毫秒
    ref_end: float | None = None
    snippet: str = ""
    confidence: float = 1.0
    note: str = ""


@dataclass
class PointResult:
    point_id: str
    description: str
    max: float
    status: str            # satisfied/partial/unsatisfied/unknown
    earned: float
    reason: str = ""
    confidence: float = 1.0


@dataclass
class EngineOutcome:
    ok: bool = True
    total: float = 0.0
    max_score: float = 0.0
    point_results: list[PointResult] = field(default_factory=list)
    penalties: list[dict] = field(default_factory=list)
    hits: list[EvidenceHit] = field(default_factory=list)
    comment: str = ""          # 建议评语
    reasoning: str = ""        # 可读解释
    confidence: float = 1.0    # 0-1
    review_level: str = LVL_NONE
    error: str = ""            # 异常可解释失败原因
    extra: dict = field(default_factory=dict)   # 题型扩展(口语四层等)


def clamp_score(v: float, lo: float = 0.0, hi: float | None = None) -> float:
    v = round(float(v), 2)
    if hi is not None:
        v = min(v, hi)
    return max(v, lo)
