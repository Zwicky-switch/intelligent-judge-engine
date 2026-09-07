"""学习建议(推荐层): 弱掌握节点 -> 先修 / 练习 / 微课."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import KnowledgeNode

# 掌握度分档
_LOW, _MID = 0.45, 0.7


def build_recommendations(db: Session, node_mastery: dict) -> list[dict]:
    """node_mastery: {node_code: {mastery, confidence, observed}}"""
    recs: list[dict] = []
    nodes = {n.code: n for n in db.query(KnowledgeNode).all()}
    weak = [{"code": c, **v} for c, v in node_mastery.items() if v["mastery"] < _MID]
    weak.sort(key=lambda x: x["mastery"])

    # 1) 先修诊断: 该节点掌握低且其先修节点也低 -> 提示先补先修
    for w in weak[:3]:
        node = nodes.get(w["code"])
        if not node:
            continue
        for pre in (node.prereq_codes or [])[:2]:
            pm = node_mastery.get(pre)
            if pm and pm["mastery"] < _MID:
                recs.append({
                    "type": "prereq",
                    "node": pre,
                    "node_name": (nodes.get(pre).name if nodes.get(pre) else pre),
                    "title": f"补《{(nodes.get(pre).name or pre)}》先修基础",
                    "priority": "high" if pm["mastery"] < _LOW else "medium",
                    "reason": f"「{w['code']}」掌握不足且其先修节点「{pre}」同样薄弱",
                })

    # 2) 弱点 -> 微课 / 练习
    for w in weak[:5]:
        code = w["code"]
        node = nodes.get(code)
        name = node.name if node else code
        if w["mastery"] < _LOW:
            recs.append({
                "type": "micro_lesson", "node": code, "node_name": name,
                "title": f"观看「{name}」微课并梳理概念", "priority": "high",
                "reason": f"掌握度 {w['mastery']:.0%}, 低于 45%, 建议先看概念微课",
            })
        else:
            recs.append({
                "type": "practice", "node": code, "node_name": name,
                "title": f"针对「{name}」完成 5 道中等难度练习", "priority": "medium",
                "reason": f"掌握度 {w['mastery']:.0%}, 需中等强度巩固",
            })
    return recs[:8]
