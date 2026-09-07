"""评分校准与评阅一致性测量(最小真实口径).

一切以已产生终审的 Score 为准, 不做外部金标准假设:
- **分数段校准**: teacher 终审分 vs 引擎分 在按引擎得分率分档的每一段的平均偏移
  (teacher - engine), 某段 |偏移| 超过阈值即被标为"需关注" —— 供教师决定是否调整引擎温度。
- **温度拟合**: 最小二乘 teacher ≈ a·engine + b (a 即"引擎→教师"温度斜率), 附 R² 与 n。
  a≈1 说明引擎与教师同量纲; a>1 说明教师给分普遍高于引擎(引擎偏严), 反之引擎偏松。
- **偏差监测 flag**: 段平均偏移 > 0.25×max 视为该段引擎分系统偏离, 上报提醒转人工抽查。

纯函数(传入 Score 可迭代对象即可), 便于单测与复用。
"""
from __future__ import annotations

import math
from statistics import fmean

# 段边界: 按 engine 得分率(0~1)五档
_BANDS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0001)]
_DEVIATION_FRAC = 0.25  # |段偏移| 超过 25% 满分 -> 标"需关注"


def _engine_ratio(engine: float, max_score: float) -> float:
    return engine / max_score if max_score > 0 else 0.0


def compute_calibration(scores, item_max: dict[int, float]) -> dict:
    """scores: 已终审的 Score 序列; item_max: {item_id: max_score}."""
    pairs = []  # (engine, teacher)
    for s in scores:
        if s.total_score is None or s.final_score is None:
            continue
        mx = item_max.get(s.item_id, s.max_score) or 1.0
        pairs.append((s.total_score, s.final_score, mx))
    n = len(pairs)

    per_band: list[dict] = []
    for lo, hi in _BANDS:
        band = [(e, t) for e, t, mx in pairs if lo <= _engine_ratio(e, mx) < hi]
        if not band:
            per_band.append({"band": f"{lo * 100:.0f}-{min(hi, 1) * 100:.0f}%",
                             "n": 0, "offset": None, "flag": False})
            continue
        offsets = [t - e for e, t in band]
        mean_off = fmean(offsets)
        max_off = max((abs(o) for o in offsets), default=0.0)
        # 用该段最大满分作段基准
        mx = max((m for _e, _t, m in pairs if lo <= _engine_ratio(_e, m) < hi), default=1.0)
        per_band.append({
            "band": f"{lo * 100:.0f}-{min(hi, 1) * 100:.0f}%",
            "n": len(band), "offset": round(mean_off, 3),
            "flag": max_off > _DEVIATION_FRAC * mx,
        })

    # 最小二乘 teacher ≈ a·engine + b
    temperature = {"a": None, "b": None, "r2": None, "n": n}
    if n >= 2:
        ex = fmean(e for e, _t, _m in pairs)
        ey = fmean(t for _e, t, _m in pairs)
        sxx = sum((e - ex) ** 2 for e, _t, _m in pairs)
        sxy = sum((e - ex) * (t - ey) for e, t, _m in pairs)
        if sxx > 0:
            a = sxy / sxx
            b = ey - a * ex
            ss_tot = sum((t - ey) ** 2 for _e, t, _m in pairs)
            ss_res = sum((t - (a * e + b)) ** 2 for e, t, _m in pairs)
            r2 = (1 - ss_res / ss_tot) if ss_tot > 0 else 1.0
            temperature = {"a": round(a, 4), "b": round(b, 4),
                           "r2": round(r2, 4), "n": n}
    flagged = [b for b in per_band if b["flag"]]
    return {
        "per_band": per_band,
        "temperature": temperature,
        "flagged_bands": [b["band"] for b in flagged],
        "note": "teacher=教师终审分, engine=引擎分; 偏移>0 表示教师给分高于引擎(引擎偏严)。"
                "flag: 段平均|偏移|>0.25×满分, 建议人工校准。",
    }


def compute_engine_teacher_consistency(scores, item_info: dict[int, dict]) -> dict:
    """engine vs 教师终审 一致性: 按题型 ±1 分容差一致率 + 平均绝对差 + n.

    终审真值取教师最终分(final_score); 仅统计确有终审的答卷。
    """
    from collections import defaultdict

    by_type: dict[str, list] = defaultdict(list)
    for s in scores:
        if s.final_score is None or s.total_score is None:
            continue
        info = item_info.get(s.item_id, {})
        by_type[info.get("type", "?")].append(
            (s.total_score, s.final_score, info.get("type_label", info.get("type", "?"))))
    out_by = {}
    total_n = 0
    total_rate = 0.0
    for t, rows in by_type.items():
        diffs = [abs(e - f) for e, f, _l in rows]
        within = sum(1 for d in diffs if d <= 1.0)
        m = len(rows)
        total_n += m
        out_by[t] = {
            "type_label": rows[0][2],
            "n": m,
            "mean_abs_diff": round(fmean(diffs), 3) if diffs else None,
            "within_1pt_rate": round(within / m, 3) if m else None,
        }
        total_rate += within
    overall = (round(total_rate / total_n, 3) if total_n else None)
    return {"by_type": out_by, "overall": overall, "n": total_n,
            "note": "口径: ±1 分内视为与教师一致(教师终审作真值); 仅统计已终审答卷。"}


def percentile(sorted_vals: list[float], p: float) -> float | None:
    """p 分位(p 为 0~1), 需已升序."""
    if not sorted_vals:
        return None
    k = max(0, min(len(sorted_vals) - 1, math.ceil(p * len(sorted_vals)) - 1))
    return sorted_vals[k]
