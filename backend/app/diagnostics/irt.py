"""IRT(2PL) 能力估计: 可插拔接口, 默认采用"分数化 Bernoulli 拟然" MLE.

方案 §5.3: Q矩阵 + IRT + BKT 组合; 本模块提供 2PL IRF 与最大似然估计,
接受每条作答的得分比例 p_i ∈[0,1] 与题目参数 (a_i 区分度, b_i 难度)。
未做真实参数标定时, a/b 使用题目配置/默认值, 结果记为"启发式 IRT 估计"。
"""
from __future__ import annotations

import math


def clamp01(x: float) -> float:
    return max(1e-6, min(1.0 - 1e-6, x))


def logit(p: float) -> float:
    return math.log(clamp01(p) / (1.0 - clamp01(p)))


def irf(theta: float, a: float, b: float) -> float:
    """2PL 正确概率 P(θ)."""
    return 1.0 / (1.0 + math.exp(-a * (theta - b)))


def _log_like(theta: float, ratios: list[float], alphas: list[float], betas: list[float]) -> float:
    s = 0.0
    for p, a, b in zip(ratios, alphas, betas):
        P = clamp01(irf(theta, a, b))
        s += p * math.log(P) + (1 - p) * math.log(1 - P)
    return s


def estimate_theta(ratios: list[float], alphas: list[float] | None = None,
                   betas: list[float] | None = None,
                   theta_range: tuple[float, float] = (-3.0, 3.0)) -> float | None:
    """分数化 Bernoulli 拟然 MLE(theta). 少于 2 条或无区分时返回 None."""
    if len(ratios) < 2:
        return None
    alphas = alphas or [1.0] * len(ratios)
    betas = betas or [0.0] * len(ratios)
    if not all(a > 0 for a in alphas):
        return None
    lo, hi = theta_range
    best_t, best_v = lo, _log_like(lo, ratios, alphas, betas)
    n = 400
    for i in range(n + 1):
        t = lo + (hi - lo) * i / n
        v = _log_like(t, ratios, alphas, betas)
        if v > best_v:
            best_v, best_t = v, t
    # 局部细化
    for _ in range(12):
        step = (hi - lo) / n / (2 ** 1)
        for dt in (-step, step):
            if best_t + dt < lo or best_t + dt > hi:
                continue
            v = _log_like(best_t + dt, ratios, alphas, betas)
            if v > best_v:
                best_v, best_t = v, best_t + dt
    return round(best_t, 3)
