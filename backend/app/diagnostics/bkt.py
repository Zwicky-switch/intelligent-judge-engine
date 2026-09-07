"""BKT(贝叶斯知识追踪)最小真实实现.

对同一 (学生, 知识节点) 的**按时序作答序列**建模, 估计"当前是否掌握该节点":

    参数(无真实大规模标定, 网格搜索 ML 拟合并如实标注):
      pL0 先验已掌握; pT 掌握后保持/转移; pG 猜对; pS 失误。
    前向更新:
      P(答对) = L·(1-pS) + (1-L)·pG
      答对/答错后的后验 -> 经 pT 转移进入下一题先验;
    末次后验即 mastery_after。

仅在观测 ≥2 次时激活(单次退化用 mastery 的统计口径, 不上 BKT)。
"""
from __future__ import annotations

import itertools
import math

_GRID = {
    "pL0": (0.15, 0.3, 0.5, 0.7, 0.85),
    "pT": (0.1, 0.3, 0.5, 0.7),
    "pG": (0.05, 0.1, 0.2, 0.3),
    "pS": (0.05, 0.1, 0.2, 0.3),
}
_EPS = 1e-9


def _forward(learned: float, successes: list[bool], pT: float,
             pG: float, pS: float) -> tuple[float, float]:
    """返回 (总对数似然, 末次后验掌握度)."""
    loglike = 0.0
    for ok in successes:
        p_correct = learned * (1 - pS) + (1 - learned) * pG
        p_correct = max(_EPS, min(1 - _EPS, p_correct))
        if ok:
            loglike += math.log(p_correct)
            learned = learned * (1 - pS) / p_correct
        else:
            loglike += math.log(1 - p_correct)
            learned = learned * pS / (1 - p_correct)
        learned = max(_EPS, min(1 - _EPS, learned))
        learned = learned + (1 - learned) * pT
    return loglike, learned


def fit_bkt(successes: list[bool]) -> dict | None:
    """网格搜索极大化序列对数似然, 回代末次后验. 少于 2 次观测返回 None."""
    successes = [bool(s) for s in successes]
    if len(successes) < 2:
        return None
    best = None
    for pL0, pT, pG, pS in itertools.product(_GRID["pL0"], _GRID["pT"],
                                             _GRID["pG"], _GRID["pS"]):
        ll, _post = _forward(pL0, successes, pT, pG, pS)
        if best is None or ll > best[0]:
            best = (ll, pL0, pT, pG, pS)
    _ll, post = _forward(best[1], successes, best[2], best[3], best[4])
    return {
        "active": True,
        "mastery_after": round(post, 3),
        "n": len(successes),
        "params": {"pL0": best[1], "pT": best[2], "pG": best[3], "pS": best[4]},
        "note": "网格搜索 ML 拟合(无大规模真参标定); ≥2 次观测才激活。",
    }
