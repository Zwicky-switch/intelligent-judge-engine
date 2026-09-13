# -*- coding: utf-8 -*-
"""双评教师间一致性统计: 三类边界用例(同分/同一教师重复/单题超两次)."""
from types import SimpleNamespace

from app.api.metrics import _double_teacher_consistency


def rec(score_id, reviewer_id, score):
    return SimpleNamespace(score_id=score_id, reviewed_by=reviewer_id,
                           new_score=float(score))


def test_same_score_two_teachers_counts_as_consistent():
    """同分: 两位不同教师给同分, 应计入一致(旧实现会误过滤)."""
    d = _double_teacher_consistency([rec(1, 3, 6.0), rec(1, 4, 6.0)])
    assert d["pairs"] == 1
    assert d["within_1pt_rate"] == 1.0
    assert d["mean_abs_diff"] == 0.0


def test_same_teacher_repeat_only_first_taken():
    """同一教师重复操作: 同 reviewer 多次记录只取首次, 不与教师自身比较."""
    d = _double_teacher_consistency([
        rec(1, 3, 6.0),   # A 第 1 次
        rec(1, 3, 7.0),   # A 重复操作(应忽略)
        rec(1, 4, 6.5),   # B
    ])
    assert d["pairs"] == 1
    assert abs(d["mean_abs_diff"] - 0.5) < 1e-9


def test_more_than_two_reviews_only_first_two_teachers():
    """单题超过两次评阅: 只取前两位不同教师, 第三位忽略."""
    d = _double_teacher_consistency([
        rec(1, 3, 6.0),
        rec(1, 4, 7.0),
        rec(1, 5, 9.0),   # 第三位教师(仲裁场景, 不计入双评对)
    ])
    assert d["pairs"] == 1
    assert abs(d["mean_abs_diff"] - 1.0) < 1e-9


def test_single_teacher_no_pair():
    """仅一位教师操作 -> 无完成对, pairs=0 如实上报."""
    d = _double_teacher_consistency([rec(1, 3, 6.0), rec(1, 3, 6.5)])
    assert d["pairs"] == 0
    assert d["within_1pt_rate"] is None
