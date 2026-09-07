"""知识掌握度 / 能力画像计算(默认算法: Q矩阵映射 + 正则加权 + IRT 辅助)."""
from __future__ import annotations

import math

from sqlalchemy.orm import Session

from app.constants import ST_AUTO_PASSED, ST_REVIEWED
from app.diagnostics import irt, qmatrix
from app.diagnostics.bkt import fit_bkt
from app.models import (
    CourseDimensionToggle, Item, Score, SkillDimension, SkillDomain,
)

SHRINK_LAMBDA = 0.6     # 正则收缩量(观察少时向 0.5 收缩)
MAX_MASTERY = 1.0


def _score_observations(db: Session, student_token: str, course_id: int) -> list[dict]:
    scores = (
        db.query(Score)
        .filter(Score.student_token == student_token,
                Score.status.in_([ST_AUTO_PASSED, ST_REVIEWED]))
        .join(Item, Item.id == Score.item_id)
        .filter(Item.course_id == course_id)
        .all()
    )
    rows = []
    for sc in scores:
        item = db.get(Item, sc.item_id)
        if item is None:
            continue
        ratio = (sc.final_score if sc.final_score is not None else sc.total_score)
        if item.max_score > 0:
            ratio = max(0.0, min(1.0, ratio / item.max_score))
        else:
            ratio = 0.0
        rows.append({"item": item, "score": sc, "ratio": ratio,
                     "a": item.discrimination or 1.0, "b": item.difficulty or 0.0})
    return rows


def compute_mastery(db: Session, student_token: str, course_id: int) -> dict:
    """返回 {node_mastery, ability(域级), dimension, theta, observed, detail}."""
    rows = _score_observations(db, student_token, course_id)
    dom_map = qmatrix.dimension_domain_map(db)
    # 课程级停用维度(absent=启用; CourseDimensionToggle 仅存 enabled=False 行)
    disabled = {r[0] for r in db.query(CourseDimensionToggle.dimension_code)
                .filter(CourseDimensionToggle.course_id == course_id,
                        CourseDimensionToggle.enabled.is_(False)).all()}

    # ---- 知识节点掌握度(正则加权) ----
    node_acc: dict[str, dict] = {}
    node_seq: dict[str, list] = {}   # BKT 时序: (作答时间/序号, 得分比例)
    for r in rows:
        for node, w in qmatrix.item_node_weights(r["item"]).items():
            acc = node_acc.setdefault(node, {"num": 0.0, "den": 0.0, "obs": 0, "disc_sum": 0.0})
            wgt = w * r["a"]
            acc["num"] += wgt * r["ratio"]
            acc["den"] += wgt
            acc["obs"] += 1
            acc["disc_sum"] += r["a"]
            node_seq.setdefault(node, []).append(
                ((r["score"].created_at, r["score"].id), r["ratio"]))

    node_mastery: dict[str, dict] = {}
    for node, acc in node_acc.items():
        lam = SHRINK_LAMBDA
        if acc["den"] > 0:
            raw = acc["num"] / acc["den"]
            mastery = (acc["num"] + lam * 0.5) / (acc["den"] + lam)
        else:
            raw = mastery = 0.5
        obs = acc["obs"]
        conf = round(min(0.96, 0.35 + 0.11 * min(obs, 6)), 3)
        # BKT: 按时序排该生在该节点上的作答序列, ≥2 观测才激活
        seq = [x[1] for x in sorted(node_seq.get(node, []), key=lambda t: (t[0][0], t[0][1]))]
        bkt = fit_bkt([s >= 0.6 for s in seq]) if len(seq) >= 2 else None
        node_mastery[node] = {
            "mastery": round(mastery, 3), "raw": round(raw, 3),
            "confidence": conf, "observed": obs,
            "bkt": bkt or {"mastery_after": None, "n": len(seq), "active": False,
                           "note": "观测不足 2 次, BKT 未激活(单轮规则)。"},
        }

    # ---- 能力域 / 二级维度(题目经由 q_matrix 的维度映射加权) ----
    domain_acc: dict[str, dict] = {}
    dim_acc: dict[str, dict] = {}
    for r in rows:
        for d in qmatrix.item_dimensions(r["item"]):
            dim = d["dimension"]
            if dim in disabled:
                continue    # 课程停用维度不参与能力画像
            w = d["weight"] * r["a"]
            dim_acc.setdefault(dim, {"num": 0.0, "den": 0.0, "obs": 0})["num"] += w * r["ratio"]
            dim_acc[dim]["den"] += w
            dim_acc[dim]["obs"] += 1
            dom = dom_map.get(dim, "domain_problem")
            acc = domain_acc.setdefault(dom, {"num": 0.0, "den": 0.0, "obs": 0, "dims": []})
            acc["num"] += w * r["ratio"]
            acc["den"] += w
            acc["obs"] += 1
            if dim not in acc["dims"]:
                acc["dims"].append(dim)

    ability: dict[str, dict] = {}
    for dom, acc in domain_acc.items():
        lam = 0.4
        score = (acc["num"] + lam * 0.5) / (acc["den"] + lam) if acc["den"] + lam else 0.5
        ability[dom] = {
            "score": round(score, 3),
            "confidence": round(min(0.95, 0.4 + 0.1 * min(acc["obs"], 5)), 3),
            "observed": acc["obs"], "dimensions": sorted(acc["dims"]),
        }

    # ---- 全量能力维度目录(60 维; 未观测 -> score=None, 前端置灰) ----
    dom_name = {d.code: d.name
                for d in db.query(SkillDomain).all()}
    dim_rows = (db.query(SkillDimension)
                .order_by(SkillDimension.domain_code, SkillDimension.order_index).all())
    dimension: dict[str, dict] = {}
    for d in dim_rows:
        dim_enabled = bool(d.enabled) and d.code not in disabled
        acc = dim_acc.get(d.code)
        if acc is None:
            dimension[d.code] = {
                "code": d.code, "label": d.name,
                "domain_code": d.domain_code,
                "domain_label": dom_name.get(d.domain_code, d.domain_code),
                "enabled": dim_enabled,
                "score": None, "observed": 0,
            }
            continue
        dimension[d.code] = {
            "code": d.code, "label": d.name,
            "domain_code": d.domain_code,
            "domain_label": dom_name.get(d.domain_code, d.domain_code),
            "enabled": dim_enabled,
            "score": round((acc["num"] + 0.3 * 0.5) / (acc["den"] + 0.3), 3)
                        if acc["den"] + 0.3 else None,
            "observed": acc["obs"],
        }

    # ---- IRT 辅助能力估计(分数化拟然 MLE) ----
    theta = None
    if len(rows) >= 2:
        theta = irt.estimate_theta([r["ratio"] for r in rows],
                                   alphas=[r["a"] for r in rows],
                                   betas=[r["b"] for r in rows])
    # ---- 画像-作答匹配度: IRF(theta,a,b) 对每题得分比例的预测优度 ----
    profile_match = None
    if len(rows) >= 2 and theta is not None:
        agrees = [1 - abs(irt.irf(theta, r["a"], r["b"]) - r["ratio"]) for r in rows]
        profile_match = {
            "value": round(sum(agrees) / len(agrees), 3),
            "method": "2PL IRF(θ,a,b) 预测每题得分比例与实得分的一致率(=1-平均绝对差)",
            "n": len(rows),
        }
    detail = (
        f"默认算法: 知识节点掌握度=按 Q 矩阵权重加权的终评分比例, 并做正则收缩(λ={SHRINK_LAMBDA}); "
        f"能力域=由节点映射的二级维度按区分度加权聚合; "
        f"IRT 层采用 2PL 分数化拟然 MLE, 题目参数用题目配置(a={[round(r['a'],2) for r in rows[:5]]}...); "
        "BKT: 对观测序列≥2 次的知识节点做网格搜索 ML 拟合并回代末次后验; "
        "profile_match=当前画像参数对既有作答的拟合优度, 供观察画像解释力。"
    )
    return {"node_mastery": node_mastery, "ability": ability,
            "dimension": dimension, "theta": theta, "profile_match": profile_match,
            "observed": len(rows), "detail": detail}


def compute_overall_confidence(data: dict) -> float:
    obs = data.get("observed", 0)
    confs = [v["confidence"] for v in data.get("ability", {}).values()]
    mean = sum(confs) / len(confs) if confs else 0.5
    return round(min(0.95, 0.4 + 0.5 * mean + 0.05 * math.log1p(obs)), 3)
