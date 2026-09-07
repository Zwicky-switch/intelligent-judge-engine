"""Q 矩阵: 题目 -> 知识节点 / 能力维度 映射工具.

约定: Item.knowledge_nodes = [node_code...]; Item.q_matrix = {node_code: {"dimension": dim_code, "weight": w}}.
能力维度 SkillDimension.code 归属 SkillDomain.domain_code(6 大域)。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Item, SkillDimension


def item_nodes(item: Item) -> list[str]:
    return list(item.knowledge_nodes or [])


def item_node_weights(item: Item) -> dict[str, float]:
    """每个知识节点对题目的考查权重(默认取题干难度的归一化? 用配置或 1)."""
    qm = item.q_matrix or {}
    out: dict[str, float] = {}
    for node in item_nodes(item):
        meta = qm.get(node) or {}
        w = float(meta.get("weight", 1.0) if isinstance(meta, dict) else 1.0)
        out[node] = w if w > 0 else 1.0
    return out


def item_dimensions(item: Item) -> list[dict]:
    """题目测查的二级能力维度: [{dimension, weight, domain}]. weight 为该题对维度的贡献."""
    qm = item.q_matrix or {}
    out = []
    for node, meta in (qm or {}).items():
        if isinstance(meta, dict) and meta.get("dimension"):
            out.append({"dimension": meta["dimension"],
                        "weight": float(meta.get("weight", 1.0) or 1.0),
                        "node": node})
    return out


def dimension_domain_map(db: Session) -> dict[str, str]:
    dims = db.query(SkillDimension.code, SkillDimension.domain_code).all()
    return {c: d for c, d in dims}
