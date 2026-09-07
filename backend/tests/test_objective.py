"""客观题判分金标准表: 覆盖全部题型 + 边界样例 + 异常输入, 题目级准确率目标 100%.

每个用例: (题型, answer_config, 满分, 学生作答, 期望得分, 期望状态或 reason 关键词)
异常样例要求: 不给静默判零, 输出可解释 error/reason。
"""
from __future__ import annotations

import pytest

from app.constants import (
    T_SINGLE_CHOICE, T_MULTIPLE_CHOICE, T_TRUE_FALSE, T_FILL_BLANK, T_NUMERIC,
    V_SATISFIED, V_PARTIAL, V_UNSATISFIED,
)
from app.engines.objective import grade_objective


# ---- 单选题 ----
SINGLE = dict(correct="B", options=["A", "B", "C", "D"])

# ---- 多选题 ----
MULTI = dict(correct=["A", "C"], scoring_mode="full")
MULTI_PARTIAL = dict(correct=["A", "C"], scoring_mode="partial")

# ---- 判断题 ----
TF_T = dict(correct=True)
TF_F = dict(correct=False)

# ---- 填空题 ----
FILL1 = dict(blanks=[{"value": "牛顿第二定律"}])
FILL2 = dict(blanks=[{"value": "9.8"}, {"value": "竖直向下"}])
FILL2_UNORDER = dict(blanks=[{"value": "9.8"}, {"value": "竖直向下"}], order_matters=False)
FILL_ALIAS = dict(blanks=[{"value": ["匀变速直线运动", "匀加速直线运动"]}])

# ---- 数值题 ----
NUM_TOL = dict(answer={"value": 9.8, "tolerance_abs": 0.05, "unit": "m/s^2"})
NUM_REL = dict(answer={"value": 6.67e-11, "tolerance_rel": 0.01, "unit": "N·m^2/kg^2"})
NUM_SIG = dict(answer={"value": 3.00e8, "tolerance_rel": 0.01, "unit": "m/s",
                       "significant_digits": 3})

GOLDEN = [
    # 单选
    (T_SINGLE_CHOICE, SINGLE, 2, "B", 2.0, V_SATISFIED),
    (T_SINGLE_CHOICE, SINGLE, 2, "答案：B", 2.0, V_SATISFIED),
    (T_SINGLE_CHOICE, SINGLE, 2, "b", 2.0, V_SATISFIED),
    (T_SINGLE_CHOICE, SINGLE, 2, "A", 0.0, V_UNSATISFIED),
    (T_SINGLE_CHOICE, SINGLE, 2, "AB", 0.0, V_UNSATISFIED),      # 单选误选
    (T_SINGLE_CHOICE, SINGLE, 2, "", 0.0, V_UNSATISFIED),         # 空答
    (T_SINGLE_CHOICE, SINGLE, 2, "我不知道", 0.0, V_UNSATISFIED),  # 无法识别
    # 多选 full
    (T_MULTIPLE_CHOICE, MULTI, 3, "A,C", 3.0, V_SATISFIED),
    (T_MULTIPLE_CHOICE, MULTI, 3, "AC", 3.0, V_SATISFIED),
    (T_MULTIPLE_CHOICE, MULTI, 3, "A,C,D", 0.0, V_UNSATISFIED),   # 多选漏/错
    (T_MULTIPLE_CHOICE, MULTI, 3, "A", 0.0, V_UNSATISFIED),        # 漏选 full 全扣
    (T_MULTIPLE_CHOICE, MULTI, 3, "A,D", 0.0, V_UNSATISFIED),      # 含错项
    (T_MULTIPLE_CHOICE, MULTI, 3, "", 0.0, V_UNSATISFIED),
    # 多选 partial: 2 空, 每对 1.5
    (T_MULTIPLE_CHOICE, MULTI_PARTIAL, 3, "A", 1.5, V_PARTIAL),
    (T_MULTIPLE_CHOICE, MULTI_PARTIAL, 3, "A,C", 3.0, V_SATISFIED),
    (T_MULTIPLE_CHOICE, MULTI_PARTIAL, 3, "A,D", 0.0, V_UNSATISFIED),  # 错一项抵消
    # 判断题
    (T_TRUE_FALSE, TF_T, 1, "T", 1.0, V_SATISFIED),
    (T_TRUE_FALSE, TF_T, 1, "对", 1.0, V_SATISFIED),
    (T_TRUE_FALSE, TF_T, 1, "正确", 1.0, V_SATISFIED),
    (T_TRUE_FALSE, TF_T, 1, "F", 0.0, V_UNSATISFIED),
    (T_TRUE_FALSE, TF_F, 1, "错", 1.0, V_SATISFIED),
    (T_TRUE_FALSE, TF_T, 1, "2", 0.0, V_UNSATISFIED),             # 异常输入有解释
    # 填空题
    (T_FILL_BLANK, FILL1, 2, "牛顿第二定律", 2.0, V_SATISFIED),
    (T_FILL_BLANK, FILL1, 2, " 牛顿 第二定律 ", 2.0, V_SATISFIED),  # 空白归一
    (T_FILL_BLANK, FILL1, 2, "动量定理", 0.0, V_UNSATISFIED),
    (T_FILL_BLANK, FILL2, 4, "9.8|竖直向下", 4.0, V_SATISFIED),
    (T_FILL_BLANK, FILL2, 4, "9.8，竖直向下", 4.0, V_SATISFIED),
    (T_FILL_BLANK, FILL2, 4, "9.8", 2.0, V_PARTIAL),              # 只答第一空
    (T_FILL_BLANK, FILL2, 4, "竖直向上|9.8", 0.0, V_UNSATISFIED),   # 顺序错误(位置敏感)
    (T_FILL_BLANK, FILL2_UNORDER, 4, "竖直向下|9.8", 4.0, V_SATISFIED),  # 顺序无关
    (T_FILL_BLANK, FILL2, 4, "", 0.0, V_UNSATISFIED),
    (T_FILL_BLANK, FILL_ALIAS, 2, "匀加速直线运动", 2.0, V_SATISFIED),  # 别名
    # 数值题
    (T_NUMERIC, NUM_TOL, 2, "9.8", 0.6, V_PARTIAL),              # 缺单位 -> unit_credit 0.3
    (T_NUMERIC, NUM_TOL, 2, "9.81 m/s^2", 2.0, V_SATISFIED),
    (T_NUMERIC, NUM_TOL, 2, "9.8 m/s^2", 2.0, V_SATISFIED),
    (T_NUMERIC, NUM_TOL, 2, "9.8 米每二次方秒", 2.0, V_SATISFIED),    # 中文单位
    (T_NUMERIC, NUM_TOL, 2, "9.8 公里/小时", 0.0, V_UNSATISFIED),    # 量纲不符
    (T_NUMERIC, NUM_TOL, 2, "9.85 m/s^2", 2.0, V_SATISFIED),        # 边界内(≤0.05)
    (T_NUMERIC, NUM_TOL, 2, "9.86 m/s^2", 0.0, V_UNSATISFIED),       # 超出绝对容差
    (T_NUMERIC, NUM_TOL, 2, "9.8 N", 0.0, V_UNSATISFIED),            # 数值对但量纲(force)不符
    (T_NUMERIC, NUM_TOL, 2, "abc", 0.0, V_UNSATISFIED),              # 无法解析
    (T_NUMERIC, NUM_TOL, 2, "", 0.0, V_UNSATISFIED),
    (T_NUMERIC, NUM_REL, 3, "6.67e-11 N·m^2/kg^2", 3.0, V_SATISFIED),
    (T_NUMERIC, NUM_REL, 3, "6.6e-11 N·m^2/kg^2", 0.0, V_UNSATISFIED),  # 相对容差 1% 外
    (T_NUMERIC, NUM_SIG, 3, "3.00e8 m/s", 3.0, V_SATISFIED),
    (T_NUMERIC, NUM_SIG, 3, "3.0e8 m/s", 2.1, V_PARTIAL),            # 有效数字不符(3 位要求)
    (T_NUMERIC, NUM_SIG, 3, "3e8 m/s", 2.1, V_PARTIAL),
]


@pytest.mark.parametrize("itype,cfg,max_sc,resp,exp_score,exp_status", GOLDEN)
def test_golden(itype, cfg, max_sc, resp, exp_score, exp_status):
    out = grade_objective(itype, cfg, resp, max_sc)
    assert out.ok, out.error
    assert abs(out.total - exp_score) < 1e-9, f"{resp!r}: {out.total} != {exp_score} | {out.reasoning}"
    assert out.hits and out.hits[0].label == exp_status, f"{resp!r}: {out.reasoning}"


def test_every_wrong_case_has_reason():
    """错误作答必须有可解释理由, 不允许静默 0 分."""
    for itype, cfg, max_sc, resp, _, _ in GOLDEN:
        out = grade_objective(itype, cfg, resp, max_sc)
        if out.total < max_sc:
            assert out.reasoning, resp
        assert out.ok


def test_idempotent():
    """幂等: 同输入重复评阅结果一致(重试不重复计分)."""
    import random
    random.seed(7)
    for _ in range(50):
        itype = random.choice([T_SINGLE_CHOICE, T_NUMERIC, T_FILL_BLANK])
        cfg = {"A": "B"} if itype == T_SINGLE_CHOICE else {"answer": {"value": 9.8, "tolerance_rel": 0.1, "unit": "m/s^2"}}
        if itype == T_FILL_BLANK:
            cfg = {"blanks": [{"value": "牛"}]}
        resp = "B" if itype == T_SINGLE_CHOICE else ("9.8 m/s^2" if itype == T_NUMERIC else "牛")
        a = grade_objective(itype, cfg, resp, 10.0)
        b = grade_objective(itype, cfg, resp, 10.0)
        assert a.total == b.total and a.reasoning == b.reasoning


def test_unsupported_type_reports_error():
    out = grade_objective("future_qtype", {}, "x", 5.0)
    assert out.ok is False and out.error
