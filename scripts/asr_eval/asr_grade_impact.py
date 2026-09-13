"""验证 ASR 错词是否影响引擎判分: 原始转写 vs 修正真值 对比判分."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.engines.subjective import grade_subjective  # noqa: E402

V1 = {"title": "牛顿第三定律", "max_score": 6, "rubric": [
    {"point_id": "P1", "description": "定律名称/大小关系", "score": 2, "slots": [
        {"label": "定律名称", "keywords": ["牛顿第三定律", "第三定律", "作用力和反作用力", "反作用力"]},
        {"label": "大小关系", "keywords": ["大小相等", "大小总是相等", "相等"]}]},
    {"point_id": "P2", "description": "方向/对象", "score": 2, "slots": [
        {"label": "方向相反", "keywords": ["方向相反", "相反", "同一条直线上", "同一直线"]},
        {"label": "作用对象", "keywords": ["两个不同物体", "两个物体", "不同物体"]}]},
    {"point_id": "P3", "description": "例子", "score": 2, "slots": [
        {"label": "例子", "keywords": ["推墙", "划船", "船桨", "我推", "火箭", "走路", "滑冰"]},
        {"label": "例子说明", "keywords": ["也推我", "水对桨", "反作用力", "推动", "向前"]}]},
]}

V2 = {"title": "动能", "max_score": 6, "rubric": [
    {"point_id": "P1", "description": "动能概念", "score": 2, "slots": [
        {"label": "概念", "keywords": ["运动具有", "运动而具有", "运动均有的能量", "由于运动", "动能"]},
        {"label": "能量", "keywords": ["能量"]}]},
    {"point_id": "P2", "description": "公式", "score": 2, "slots": [
        {"label": "公式形式", "keywords": ["EK", "Ek", "二分之一", "1/2", "½", "MV方", "mv方", "V的平方"]},
        {"label": "公式要素", "keywords": ["质量", "速度", "平方"]}]},
    {"point_id": "P3", "description": "因素与例子", "score": 2, "slots": [
        {"label": "影响因素", "keywords": ["质量", "速度", "质量和速度", "质量与速度"]},
        {"label": "例子", "keywords": ["小车", "卡车", "汽车", "刹车", "跑得快", "速度越大"]}]},
]}

cases = [
    ("录音1 ASR原文", V1,
     "牛顿第三定律两个物体之间的作用力和反作用力大小相等方向相反作用在同一条直线上例子我推强 强也推我"),
    ("录音1 修正真值", V1,
     "牛顿第三定律两个物体之间的作用力和反作用力大小相等方向相反作用在同一条直线上例子我推墙墙也推我"),
    ("录音2 ASR原文", V2,
     "动能是物体运动均有的能量,公式EK等于二分之一M为方,动能和物体质量速度有关。比如跑的快的小车都能更大,重的卡车和小车同样速度,卡车都能更大。"),
    ("录音2 修正真值", V2,
     "动能是物体运动具有的能量,公式EK等于二分之一MV方,动能和物体质量速度有关。比如跑得快的小车动能更大,重的卡车和小车同样速度,卡车动能更大。"),
    ("录音4 ASR原文", V2,
     "动能 物体具有运动而具有的能量 叫做动能动能公式 1K 等于 1⁴ M 乘 V 的平方动能大小 有物体质量和 M 和顺时速度 V 两个因素决定举例 同一辆汽车速度越大 动能越大高速行驶时 刹车距离更长相同速度行驶 满载大货车比小较车质量更大动能更大 发生碰撞时 拋坏力更强"),
    ("录音4 修正真值", V2,
     "动能 物体具有运动而具有的能量 叫做动能动能公式 EK 等于 二分之一 M 乘 V 的平方动能大小 有物体质量和 M 和瞬时速度 V 两个因素决定举例 同一辆汽车速度越大 动能越大高速行驶时 刹车距离更长相同速度行驶 满载大货车比小轿车质量更大动能更大 发生碰撞时 破坏力更强"),
]

print("=" * 60)
print("ASR 错词对判分影响对比 (引擎语义槽判分)")
print("=" * 60)
for label, item, text in cases:
    out = grade_subjective(item, text, llm=None, quality={})
    print(f"  {label}: {out.total:.1f}/{item['max_score']}")

print("\n结论: 若 ASR 原文与修正真值得分一致, 说明错词(同音字)不影响判分;")
print("若不一致, 说明需在量规中补充 ASR 易错变体或启用大模型复核。")
