"""演示种子数据(第一次启动自动注入; 可用 python -m app.seeds.demo --reset 重建).

《大学物理·力学》课程/章节/知识节点 + 6×10 能力体系 + 覆盖各题型的题目(Q 矩阵就位)
+ 强/中/弱 三名学生及完整答卷, 种子评阅后诊断/雷达/复核队列开箱即有真实形态。

Q 矩阵映射口径(每知识节点 -> 一个主测二级能力维度):
  客观计算题按“计算/推理”归入 problem 域; 概念/边界辨析归入 knowledge 域;
  守恒条件的“反例意识”判别归入 critical 域; 口语题主测表达-结构组织;
  实操视频题(阶段 2)映射实践-步骤执行。维度代码 = 域前缀 + 序号(与下方表一致)。
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.constants import (
    T_SINGLE_CHOICE, T_MULTIPLE_CHOICE, T_TRUE_FALSE, T_FILL_BLANK, T_NUMERIC,
    T_SUBJECTIVE_TEXT, T_SPOKEN, T_VIDEO, T_FORMULA,
    ROLE_ADMIN, ROLE_PROP_TEACHER, ROLE_GRADER, ROLE_STUDENT,
    ST_AUTO_PASSED, ST_REVIEWED, LVL_SAMPLE,
)
from app.core.security import hash_password
from app.db import SessionLocal, init_db
from app.parsers.text import quality_gate_text
from app.models import (
    Answer, Chapter, Course, Item, ItemVersion, KnowledgeNode,
    RubricTemplate, Score, SkillDimension, SkillDomain, User,
)

# ============================================================
# 1) 课程与知识结构
# ============================================================

def _seed_course(db: Session) -> Course:
    course = Course(code="PHY-101", name="大学物理（力学）",
                    description="质点运动学、牛顿运动定律、功与能量；对应方案力学示例 PHY-2026。")
    db.add(course)
    db.flush()
    chaps = [
        ("质点运动学", [
            ("K-位置与位移", "位置、位移、路程与参考系"),
            ("K-速度与加速度", "平均/瞬时速度、加速度、匀变速运动公式"),
        ]),
        ("牛顿运动定律", [
            ("K-受力分析", "隔离法受力分析、正交分解、常见力"),
            ("K-牛顿第二定律", "F=ma、瞬时性、矢量性、惯性系"),
            ("K-牛顿第三定律", "作用力与反作用力的关系与区别"),
        ]),
        ("功与能量", [
            ("K-功与功率", "功的定义、变力做功、功率"),
            ("K-动能定理", "合外力做功与动能变化的关系"),
            ("K-机械能守恒", "守恒条件(只有重力/弹力做功)与能量转化"),
        ]),
    ]
    node_map: dict[str, KnowledgeNode] = {}
    for cidx, (cname, nodes) in enumerate(chaps):
        ch = Chapter(course_id=course.id, order_index=cidx, name=cname)
        db.add(ch)
        db.flush()
        for code, desc in nodes:
            kn = KnowledgeNode(chapter_id=ch.id, code=code,
                               name=code.split("-", 1)[1], description=desc)
            db.add(kn)
            db.flush()
            node_map[code] = kn
    # 先修链(供 recommender 使用)
    prereq_map = {
        "K-速度与加速度": ["K-位置与位移"],
        "K-牛顿第二定律": ["K-受力分析", "K-速度与加速度"],
        "K-牛顿第三定律": ["K-受力分析"],
        "K-动能定理": ["K-牛顿第二定律"],
        "K-机械能守恒": ["K-功与功率", "K-动能定理"],
    }
    for code, pres in prereq_map.items():
        node_map[code].prereq_codes = pres
    db.commit()
    return course


# ============================================================
# 2) 6 大能力域 × 10 二级维度 = 60 (顺序即维度序号)
# ============================================================

# (domain_code, prefix, domain_name, [10 个二级维度名])
_DIM_MATRIX = [
    ("domain_knowledge", "KN", "知识理解",
     ["概念理解", "术语掌握", "事实识记", "原理领悟", "关系梳理", "边界辨析",
      "记忆保持", "迁移准备", "错误辨析", "知识整合"]),
    ("domain_problem", "PS", "问题解决",
     ["信息提取", "问题表征", "策略选择", "建模", "推理", "计算", "验证",
      "纠错", "举例", "迁移"]),
    ("domain_practice", "PR", "实践操作",
     ["工具选择", "准备规范", "步骤执行", "时序控制", "精度控制", "效率",
      "安全规范", "故障处理", "结果记录", "质量控制"]),
    ("domain_expression", "EX", "表达沟通",
     ["发音", "语速节奏", "停顿", "词汇丰富", "语法完整", "结构组织", "术语使用",
      "图表表达", "论据组织", "答辩回应"]),
    ("domain_critical", "CR", "批判与创新",
     ["证据意识", "假设提出", "比较分析", "因果分析", "反例意识", "方案优化",
      "跨域联结", "原创性", "风险意识", "反思评价"]),
    ("domain_transfer", "TR", "学习迁移",
     ["自主检索", "元认知", "学习计划", "时间管理", "协作", "反馈利用",
      "知识迁移", "情境适应", "持续改进", "职业规范"]),
]


def seed_dimensions(db: Session) -> None:
    """写入 6 能力域 + 60 二级维度. 维度代码 = 前缀 + 序号(1..10)."""
    for didx, (dom_code, _prefix, dom_name, _dims) in enumerate(_DIM_MATRIX):
        db.add(SkillDomain(code=dom_code, name=dom_name, order_index=didx))
    db.flush()
    for dom_code, prefix, _dom_name, dims in _DIM_MATRIX:
        for i, dim_name in enumerate(dims, start=1):
            db.add(SkillDimension(domain_code=dom_code, code=f"{prefix}{i}",
                                  name=dim_name, definition="", enabled=True,
                                  order_index=i, weight=1.0))
    db.commit()


# ============================================================
# 3) 题目定义(答案配置 / 量规 / Q 矩阵 / 难度与区分度)
# ============================================================

def _it(code: str, itype: str, chapter: str, stem: str, max_score: float,
        answer_config: dict, rubric: list | None, reference: str,
        nodes: list, qm: dict, policy: dict | None = None,
        difficulty=0.0, discrimination=1.0) -> dict:
    return {"code": code, "type": itype, "chapter": chapter, "title": stem,
            "max_score": max_score, "answer_config": answer_config, "rubric": rubric or [],
            "reference_answer": reference, "knowledge_nodes": nodes, "q_matrix": qm,
            "scoring_policy": policy or {}, "cognitive_level": "apply",
            "difficulty": difficulty, "discrimination": discrimination}


def _items() -> list[dict]:
    """题目定义(章节用名字, 由 seed_all 映射到 chapter_id)."""
    return [
        # ---------- 客观题(知识/问题域) ----------
        _it("PHY-2026-001", T_SINGLE_CHOICE, "质点运动学",
            "下列物理量中属于矢量的是（　）\nA. 速度　B. 时间　C. 温度　D. 路程", 2,
            {"correct": "A"}, None, "速度是矢量，有大小也有方向。",
            ["K-位置与位移"], {"K-位置与位移": {"dimension": "KN1", "weight": 1.0}},
            difficulty=-1.2),
        _it("PHY-2026-002", T_SINGLE_CHOICE, "质点运动学",
            "质点从静止开始做匀加速直线运动，加速度 a=2 m/s²，则第 3 s 末的速度为（　）\nA. 4 m/s　B. 6 m/s　C. 8 m/s　D. 12 m/s", 2,
            {"correct": "B"}, None, "v=at=2×3=6 m/s。",
            ["K-速度与加速度"], {"K-速度与加速度": {"dimension": "PS6", "weight": 1.0}},
            difficulty=-0.6),
        _it("PHY-2026-003", T_SINGLE_CHOICE, "牛顿运动定律",
            "由牛顿第二定律 F=ma 可知，物体所受合外力一定时，质量越大其加速度（　）\nA. 越大　B. 越小　C. 不变　D. 无法确定", 2,
            {"correct": "B"}, None, "a=F/m，合外力一定时质量越大加速度越小。",
            ["K-牛顿第二定律"], {"K-牛顿第二定律": {"dimension": "KN5", "weight": 1.0}},
            difficulty=-0.8),
        _it("PHY-2026-004", T_TRUE_FALSE, "牛顿运动定律",
            "判断：作用力与反作用力大小相等、方向相反、作用在同一直线上，二者作用在同一物体上。（　）", 1,
            {"correct": False}, None, "作用力与反作用力作用在相互作用的两个不同物体上。",
            ["K-牛顿第三定律"], {"K-牛顿第三定律": {"dimension": "KN6", "weight": 1.0}},
            difficulty=-0.4),
        _it("PHY-2026-005", T_FILL_BLANK, "牛顿运动定律",
            "牛顿第二定律表达式为 F=____；国际单位制中力的单位是____；应用时须选取____参考系。", 3,
            {"blanks": [{"value": ["ma", "m*a", "m·a"]},
                        {"value": ["牛", "牛顿", "N"]},
                        {"value": "惯性"}],
             "order_matters": True}, None,
            "F=ma；牛/牛顿(N)；惯性(参考)系。",
            ["K-牛顿第二定律"], {"K-牛顿第二定律": {"dimension": "KN2", "weight": 1.0}},
            difficulty=-0.3),
        _it("PHY-2026-006", T_NUMERIC, "牛顿运动定律",
            "质量 m=2 kg 的物体受到合外力 F=10 N，求其加速度大小 a。", 2,
            {"answer": {"value": 5.0, "tolerance_abs": 0.05, "unit": "m/s^2",
                        "unit_credit": 0.3}}, None,
            "a=F/m=10/2=5 m/s²。",
            ["K-牛顿第二定律"], {"K-牛顿第二定律": {"dimension": "PS6", "weight": 1.0}},
            difficulty=0.0),
        _it("PHY-2026-007", T_MULTIPLE_CHOICE, "牛顿运动定律",
            "下列力中属于接触力的是（　）(多选)\nA. 弹力　B. 摩擦力　C. 万有引力　D. 电磁力", 3,
            {"correct": ["A", "B"], "scoring_mode": "partial"}, None,
            "弹力与摩擦力需要两物体直接接触并产生形变/相对运动趋势。",
            ["K-受力分析"], {"K-受力分析": {"dimension": "KN1", "weight": 1.0}},
            difficulty=-0.5),
        _it("PHY-2026-008", T_NUMERIC, "功与能量",
            "质量为 1 kg 的物体以 10 m/s 匀速运动，其动能 E_k 为多少？", 2,
            {"answer": {"value": 50.0, "tolerance_abs": 0.2, "unit": "J",
                        "unit_credit": 0.3}}, None,
            "E_k=½mv²=½×1×10²=50 J。",
            ["K-动能定理"], {"K-动能定理": {"dimension": "PS6", "weight": 1.0}},
            difficulty=0.0),
        _it("PHY-2026-009", T_SINGLE_CHOICE, "功与能量",
            "下列哪种力做功与路径无关（保守力）？（　）\nA. 滑动摩擦力　B. 重力　C. 空气阻力　D. 绳子拉力", 2,
            {"correct": "B"}, None, "重力为保守力，做功只取决于始末位置。",
            ["K-功与功率"], {"K-功与功率": {"dimension": "KN1", "weight": 1.0}},
            difficulty=0.1),
        _it("PHY-2026-010", T_MULTIPLE_CHOICE, "功与能量",
            "下列关于机械能守恒的说法正确的有（　）(多选)\nA. 只有重力(或系统内弹力)做功时系统机械能守恒\nB. 只要存在摩擦力做功，机械能就一定不守恒\nC. 轻弹簧与小球系统只在弹力做功时，系统机械能守恒\nD. 物体做匀速直线运动时，机械能一定守恒", 3,
            {"correct": ["A", "C"], "scoring_mode": "partial"}, None,
            "判定守恒要看是否有重力/弹力之外的力做功(B 错在绝对化，D 反例如匀速上升)。",
            ["K-机械能守恒"], {"K-机械能守恒": {"dimension": "CR5", "weight": 1.0}},
            difficulty=0.7, discrimination=1.2),

        # ---------- 文本主观题 ----------
        _it("PHY-2026-020", T_SUBJECTIVE_TEXT, "牛顿运动定律",
            "质量 m=2 kg 的物体静止于水平地面，受到与水平方向成 37° 斜向上的拉力 F=25 N。"
            "物体与地面间动摩擦因数 μ=0.2，g 取 10 m/s²，sin37°=0.6，cos37°=0.8。"
            "请：①作出受力分析；②列出竖直与水平方向的动力学方程；③求出加速度大小并说明单位。", 8,
            {}, [
                {"point_id": "P1", "score": 3,
                 "description": "正确作出受力分析(重力、支持力、拉力、滑动摩擦力)",
                 "keywords": ["受力分析", "重力", "支持力", "拉力", "摩擦力"]},
                {"point_id": "P2", "score": 3,
                 "description": "正交分解，建立竖直/水平方向动力学方程",
                 "keywords": ["正交分解", "N=mg-Fsin37", "Fcos37°-f=ma", "f=μN"]},
                {"point_id": "P3", "score": 2,
                 "description": "算出加速度数值并给出正确单位",
                 "keywords": ["9.5", "m/s^2"]},
            ],
            "受力分析：重力 mg=20N 竖直向下；支持力 N 竖直向上；拉力 F=25N 斜向上；滑动摩擦力 f 水平向后。"
            "把拉力正交分解，竖直方向 N+Fsin37°=mg → N=20-15=5N；f=μN=1N；"
            "水平方向 Fcos37°-f=ma → a=(20-1)/2=9.5 m/s²，方向水平向右。",
            ["K-受力分析", "K-牛顿第二定律"],
            {"K-受力分析": {"dimension": "PS2", "weight": 0.6},
             "K-牛顿第二定律": {"dimension": "PS6", "weight": 0.4}},
            policy={"review_threshold": 0.72, "penalties": [
                {"reason": "受力分析遗漏或多了作用在别的物体上的力", "max": 1.0},
                {"reason": "单位错误或遗漏", "max": 0.5},
            ]},
            difficulty=1.1, discrimination=1.4),

        # ---------- 口语题 ----------
        _it("PHY-2026-030", T_SPOKEN, "牛顿运动定律",
            "请用一段约 40 秒的陈述，讲清牛顿第二定律的内容、公式，并给出一个生活中与惯性/加速度相关的应用。", 5,
            {"term_bank": ["加速度", "合外力", "质量", "成正比", "惯性"]}, [
                {"point_id": "P1", "score": 2,
                 "description": "正确表述定律内容(加速度与合外力成正比、与质量成反比)",
                 "keywords": ["加速度", "合外力", "质量", "成正比"]},
                {"point_id": "P2", "score": 1,
                 "description": "说出公式 F=ma",
                 "keywords": ["F=ma", "ma", "等于"]},
                {"point_id": "P3", "score": 2,
                 "description": "给出一个生活应用并解释(如急刹车/惯性)",
                 "keywords": ["刹车", "急停", "惯性", "前倾"]},
            ],
            "物体的加速度大小与合外力成正比、与质量成反比，方向与合外力相同，公式 F=ma。"
            "应用：坐公交车急刹车时身体前倾，体现惯性；刹车让车减速正是地面摩擦力使车产生反向加速度。",
            ["K-牛顿第二定律"],
            {"K-牛顿第二定律": {"dimension": "EX6", "weight": 1.0}},
            policy={"spoken_weights": {"pronunciation": 0.25, "fluency": 0.25,
                                       "expression": 0.25, "content": 0.25}},
            difficulty=0.3, discrimination=1.0),

        # ---------- 实操视频题(阶段 2 接口占位) ----------
        _it("PHY-2026-040", T_VIDEO, "功与能量",
            "实验：用打点计时器验证机械能守恒。请按规范完成安装、操作、读数与数据处理，并上传过程视频。", 10,
            {}, [
                {"step_id": "S1", "description": "正确安装打点计时器、纸带与重物，并接通电源"},
                {"step_id": "S2", "description": "先通电后释放纸带，操作顺序规范"},
                {"step_id": "S3", "description": "正确选取计数点并读取、记录数据"},
                {"step_id": "S4", "description": "计算验证机械能守恒，并分析误差来源"},
            ], "", ["K-机械能守恒"],
            {"K-机械能守恒": {"dimension": "PR3", "weight": 1.0}},
            policy={"review_threshold": 0.8}, difficulty=1.5, discrimination=1.2),

        # ---------- 双评示例题(review_mode=double, 待两位独立教师复核) ----------
        _it("PHY-2026-050", T_SUBJECTIVE_TEXT, "功与能量",
            "物体从距地面 h=5 m 处由静止自由下落，取 g=10 m/s²，忽略空气阻力。"
            "请用动能定理求出物体落地瞬间的速度大小，并说明你的列式依据。", 6,
            {}, [
                {"point_id": "P1", "score": 2,
                 "description": "写出动能定理：合外力(重力)做的总功等于动能变化量",
                 "keywords": ["动能定理", "总功", "mgh", "½mv²", "重力做功"]},
                {"point_id": "P2", "score": 2,
                 "description": "质量约去并正确代入 h=5、g=10，解出 v=10 m/s",
                 "keywords": ["约去", "√(2gh)", "10 m/s", "代入"]},
                {"point_id": "P3", "score": 2,
                 "description": "说明列式依据(初态静止、只有重力做功/忽略阻力)",
                 "keywords": ["初态静止", "只有重力做功", "忽略空气阻力"]},
            ],
            "由动能定理，合外力做的总功等于物体动能的变化量。物体从静止自由下落只受重力、忽略空气阻力，"
            "初动能为零，故 mgh=½mv²−0，质量 m 约去得 v=√(2gh)=√(2×10×5)=10 m/s。",
            ["K-动能定理"],
            {"K-动能定理": {"dimension": "PS6", "weight": 1.0}},
            policy={"review_mode": "double", "review_threshold": 0.7},
            difficulty=0.2, discrimination=1.0),

        # ---------- 双人复核发布示例(草稿, 未发布: 演示"2 个不同账号复核后真正发布") ----------
        _it("PHY-2026-060", T_SUBJECTIVE_TEXT, "功与能量",
            "草稿示例题：请解释为什么跳伞运动员在匀速下降阶段机械能不守恒，并指出能量去向。", 4,
            {}, [
                {"point_id": "P1", "score": 2,
                 "description": "指出匀速下降动能不变、重力势能减小, 机械能不守恒",
                 "keywords": ["动能", "重力势能", "机械能不守恒"]},
                {"point_id": "P2", "score": 2,
                 "description": "说明减少的机械能转化为内能(克服空气阻力做功)",
                 "keywords": ["空气阻力", "内能", "转化为"]},
            ],
            "匀速下降阶段动能不变而重力势能减小, 机械能不守恒; 减小的机械能用于克服空气阻力做功, 转化为内能。",
            ["K-机械能守恒"],
            {"K-机械能守恒": {"dimension": "CR5", "weight": 1.0}},
            policy={"review_mode": "double", "review_threshold": 0.7,
                    "require_double_publish": True},
            difficulty=0.4, discrimination=1.0),

        # ---------- 公式符号化题(新题型: 字母表达式等价判定) ----------
        _it("PHY-2026-070", T_FORMULA, "牛顿运动定律",
            "已知某物体受到的合外力大小为 F、质量为 m(均取正值, F 与 m 采用国际单位)。"
            "请用 F 与 m 写出该物体加速度 a 的表达式(例如 F/m)。", 3,
            {"formula": {"expected": "F/m",
                         "variables": [{"name": "F", "min": 1.0, "max": 12.0},
                                       {"name": "m", "min": 1.0, "max": 12.0}]}},
            None, "a=F/m(由牛顿第二定律 a=F/m, 加速度与合外力成正比、与质量成反比)。",
            ["K-牛顿第二定律"], {"K-牛顿第二定律": {"dimension": "PS6", "weight": 1.0}},
            difficulty=0.0, discrimination=1.0),
    ]


# ============================================================
# 4) 学生与答卷(强/中/弱 三档, 客观题答案、主观题文本、口语转写)
# ============================================================

# code -> [强, 中, 弱] 客观题作答串
_OBJECTIVE_ANSWERS: dict[str, list[str]] = {
    "PHY-2026-001": ["A", "A", "D"],
    "PHY-2026-002": ["B", "B", "A"],
    "PHY-2026-003": ["B", "B", "A"],
    "PHY-2026-004": ["F", "T", "T"],
    "PHY-2026-005": ["ma|牛顿|惯性", "ma|牛|惯性", "F=ma|N|惯性"],
    "PHY-2026-006": ["5 m/s^2", "5 m/s^2", "4.9 m/s^2"],
    "PHY-2026-007": ["A,B", "A,C", "C,D"],
    "PHY-2026-008": ["50 J", "50 J", "25 J"],
    "PHY-2026-009": ["B", "B", "A"],
    "PHY-2026-010": ["A,C", "A", "B,D"],
}

_STRONG_SUBJ = ("受力分析：物体受重力 G=mg=20N，竖直向下；地面对它的支持力 N，竖直向上；"
                "拉力 F=25N，与水平成 37° 斜向上；地面对物体的滑动摩擦力 f，水平向后。"
                "把拉力正交分解：水平分力 Fcos37°=20N，竖直分力 Fsin37°=15N。"
                "竖直方向平衡：N+Fsin37°=mg，所以 N=mg-Fsin37°=20-15=5N；f=μN=0.2×5=1N。"
                "水平方向由牛顿第二定律列方程 Fcos37°-f=ma，即 20-1=2a，"
                "解得 a=9.5m/s^2，方向沿水平向右，加速度单位是米每二次方秒。")
_MID_SUBJ = ("物体受重力、支持力、拉力和滑动摩擦力。竖直方向 N+Fsin37°=mg，得 N=5N；"
             "f=μN=1N；水平方向 Fcos37°-f=ma，代入得 a=(20-1)/2=9.5 m/s^2。"
             "受力分析列出来了，但没画示意图，正交分解部分写得比较省略。")
_WEAK_SUBJ = ("这题用牛顿第二定律做，直接 F=ma，a=25/2=12.5。")

_STRONG_SPOKEN = ("牛顿第二定律说的是，物体的加速度大小和它受到的合外力成正比，和它的质量成反比，"
                  "加速度方向与合外力方向相同，公式是 F=ma。"
                  "举个例子，坐公交车时司机突然急刹车，车上的人身体会往前倾，这就是惯性；"
                  "刹车时地面给车很大的摩擦力让车产生向后的加速度，车才停下来。")
_MID_SPOKEN = ("牛顿第二定律是 F 等于 m a，说的是力和加速度还有质量的关系。质量越大的东西越不容易改变运动状态，"
               "合外力越大加速度就越大，比如重的车和轻的车。")
_WEAK_SPOKEN = ("如图。就是 如图 所示的内容，老师上课讲过，我忘了。")

# 双评示例题作答(中档, 物理过程自洽; 供两位教师独立复核演示)
_MID_DOUBLE = ("由动能定理，合外力做的总功等于物体动能的变化量。物体自由下落只受重力作用，忽略空气阻力，"
               "初速度为零，所以 mgh=½mv²−0。方程两边质量 m 约去，得 v=√(2gh)。代入 h=5 m、g=10 m/s²，"
               "v=√(2×10×5)=10 m/s。依据是初态静止、只有重力做功。")

_STUDENTS = [
    {"username": "student_li", "name": "李雪", "token": "stu_A7k2",
     "subj": _STRONG_SUBJ, "spoken": _STRONG_SPOKEN},
    {"username": "student_wang", "name": "王哲", "token": "stu_B9q4",
     "subj": _MID_SUBJ, "spoken": _MID_SPOKEN},
    {"username": "student_zhao", "name": "赵晨", "token": "stu_C2m8",
     "subj": _WEAK_SUBJ, "spoken": _WEAK_SPOKEN},
]


def _mk_user(username: str, name: str, role: str, password: str,
             token: str | None = None) -> User:
    salt, h = hash_password(password)
    return User(username=username, display_name=name, role=role,
                password_hash=h, salt=salt, student_token=token, active=True)


def _seed_users(db: Session, course: Course) -> None:
    db.add_all([
        _mk_user("admin", "教务管理员", ROLE_ADMIN, "admin123"),
        _mk_user("prop_teacher", "陈老师（命题）", ROLE_PROP_TEACHER, "teacher123"),
        _mk_user("grader", "张老师（阅卷）", ROLE_GRADER, "teacher123"),
        # 双评第二位独立阅卷教师(与 grader 不同账号, 才满足"两位不同教师")
        _mk_user("grader2", "刘老师（阅卷二）", ROLE_GRADER, "teacher123"),
    ])
    db.flush()
    for s in _STUDENTS:
        u = _mk_user(s["username"], s["name"], ROLE_STUDENT, "stu123", s["token"])
        u.course_id = course.id
        db.add(u)
    db.commit()


def _spoken_sidecar_segments(text: str) -> list[dict]:
    """为演示样本生成**确定性**词级时间戳侧车(来源标注 manual_sidecar).

    目的: 在未接入真实 ASR 的离线演示里, 让口语"语流流畅层"的
    时间戳计算路径真实跑通一次。绝不是真实发音对齐 —— 发音层与
    真实流畅指标仍须接入 ASR/强制对齐后才算数(界面如实提示)。
    节奏按 ~2 字/词、词间 ~120ms 停顿合成, 无需随机, 幂等可复现。
    """
    tokens: list[str] = []
    for chunk in re.split(r"[，。；！？、,\s;!?]+", text or ""):
        if not chunk:
            continue
        tokens.extend(chunk[i:i + 2] for i in range(0, len(chunk), 2))
    if not tokens:
        return []
    words, cursor = [], 0
    for t in tokens:
        dur = 360
        words.append({"word": t, "start": cursor, "end": cursor + dur})
        cursor += dur + 120  # 词间短停顿(<=400ms, 不计为明显犹豫停顿)
    return [{"text": text, "start": 0, "end": cursor,
             "source": "manual_sidecar", "words": words}]


def _seed_answers(db: Session, items: dict[str, Item]) -> None:
    for si in range(3):
        tok = _STUDENTS[si]["token"]
        for code, resp in _OBJECTIVE_ANSWERS.items():
            r = resp[si].strip()
            db.add(Answer(trace_id=f"seed-{si}-{code}", student_token=tok,
                          item_id=items[code].id, modality="text",
                          content=r, raw_response=r,
                          quality=quality_gate_text(r, item_type=items[code].type)))
        subj_text = _STUDENTS[si]["subj"].strip()
        db.add(Answer(trace_id=f"seed-{si}-subj", student_token=tok,
                      item_id=items["PHY-2026-020"].id, modality="text",
                      content=subj_text, raw_response=subj_text,
                      quality=quality_gate_text(subj_text, item_type="subjective_text")))
        # 口语题: 以人工誊抄转写文本为内容(演示无 ASR 时的可靠证据来源)
        sp_text = _STUDENTS[si]["spoken"].strip()
        q = quality_gate_text(sp_text, item_type="spoken")
        q["note_asr"] = "manual_transcript"
        # 强学生样本附带词级时间戳侧车 -> 流畅层在无真实 ASR 时也能演示真实计算路径
        segs = _spoken_sidecar_segments(sp_text) if si == 0 else []
        db.add(Answer(trace_id=f"seed-{si}-spoken", student_token=tok,
                      item_id=items["PHY-2026-030"].id, modality="audio",
                      content=sp_text, raw_response="", content_uri="", segments=segs,
                      quality=q))
        # 双评示例题: 仅中档生作答, 保持"待两位独立教师复核"状态(不自动终审)
        if si == 1:
            dt = _MID_DOUBLE.strip()
            db.add(Answer(trace_id="seed-1-double", student_token=tok,
                          item_id=items["PHY-2026-050"].id, modality="text",
                          content=dt, raw_response=dt,
                          quality=quality_gate_text(dt, item_type="subjective_text")))
        # 公式符号化题: 仅弱档生作答, 正确答案 F/m -> 确定性自动判满
        if si == 2:
            fmt = "F/m"
            db.add(Answer(trace_id="seed-2-formula", student_token=tok,
                          item_id=items["PHY-2026-070"].id, modality="text",
                          content=fmt, raw_response=fmt,
                          quality=quality_gate_text(fmt, item_type="formula")))
    db.commit()


def grade_seed_answers(db: Session, llm=None) -> dict:
    """评阅全部未评 seed 答卷: 客观自动放行; 抽样档自动模拟教师接受(诊断开箱完整),
    强制档(证据不足/引图等)留在复核队列供阅卷台演示."""
    from app.orchestrator.runner import default_llm, grade_answer
    llm = llm if llm is not None else default_llm()
    stats = {"total": 0, "auto": 0, "needs_review": 0, "sampled_accepted": 0,
             "double_pending": 0}
    answers = db.query(Answer).filter(Answer.graded.is_(False)).all()
    for ans in answers:
        it = db.get(Item, ans.item_id)
        # 双评题(独立双阅卷): 种子不代替教师做自动终审, 保留待评状态供两位教师复核
        double_item = bool(it and (it.scoring_policy or {}).get("review_mode") == "double")
        score = grade_answer(db, ans, llm=llm)
        if score is None:
            continue
        stats["total"] += 1
        if score.status == ST_AUTO_PASSED:
            stats["auto"] += 1
            continue
        stats["needs_review"] += 1
        if double_item:
            stats["double_pending"] += 1
            continue
        if score.review_level == LVL_SAMPLE:
            score.status = ST_REVIEWED
            score.final_score = score.total_score
            score.review_round = 1
            score.reviewed_at = datetime.now(timezone.utc)
            stats["sampled_accepted"] += 1
    db.commit()
    return stats


# ============================================================
# 5) 入口
# ============================================================

def seed_all(db: Session) -> dict:
    course = _seed_course(db)
    seed_dimensions(db)
    ch_map = {c.name: c.id
              for c in db.query(Chapter).filter(Chapter.course_id == course.id).all()}
    items: dict[str, Item] = {}
    for it in _items():
        obj = Item(code=it["code"], type=it["type"], chapter_id=ch_map[it["chapter"]],
                   course_id=course.id, title=it["title"], max_score=it["max_score"],
                   answer_config=it["answer_config"], rubric=it["rubric"],
                   reference_answer=it["reference_answer"],
                   knowledge_nodes=it["knowledge_nodes"], q_matrix=it["q_matrix"],
                   scoring_policy=it["scoring_policy"],
                   cognitive_level=it["cognitive_level"],
                   difficulty=it["difficulty"], discrimination=it["discrimination"])
        db.add(obj)
        db.flush()
        # 双人复核发布示例保持草稿(未发布), 供界面演示"两位不同账号复核后发布"
        demo_draft = it["code"] == "PHY-2026-060"
        if not demo_draft:
            db.add(ItemVersion(item_id=obj.id, version=1, rubric=obj.rubric,
                               answer_config=obj.answer_config,
                               reference_answer=obj.reference_answer,
                               knowledge_nodes=obj.knowledge_nodes,
                               q_matrix=obj.q_matrix,
                               max_score=obj.max_score, scoring_policy=obj.scoring_policy,
                               published_by=None))
            obj.published = True
        items[it["code"]] = obj
    # 量规模板示例(命题编辑页"套用模板"下拉)
    db.add_all([
        RubricTemplate(name="物理计算说理三段式", subject="物理", course_id=course.id,
                       description="受力/对象分析 → 列方程(写明依据) → 求解与单位结论; 常见于力学计算主观题。",
                       rubric=[
                           {"point_id": "P1", "score": 2,
                            "description": "受力/对象分析正确",
                            "keywords": ["受力分析", "对象", "重力", "支持力", "摩擦力"]},
                           {"point_id": "P2", "score": 2,
                            "description": "正确列出动力学方程并写明依据",
                            "keywords": ["牛顿第二定律", "F=ma", "方程", "依据"]},
                           {"point_id": "P3", "score": 2,
                            "description": "求出结果并给出正确单位",
                            "keywords": ["m/s^2", "解得", "单位"]},
                       ]),
        RubricTemplate(name="物理实验设计题", subject="物理", course_id=course.id,
                       description="实验设计题: 原理依据 → 器材与步骤 → 数据处理与误差分析。",
                       rubric=[
                           {"point_id": "P1", "score": 2,
                            "description": "写明实验原理依据",
                            "keywords": ["原理", "依据", "公式"]},
                           {"point_id": "P2", "score": 2,
                            "description": "器材选择与操作步骤规范",
                            "keywords": ["器材", "步骤", "接通电源", "释放"]},
                           {"point_id": "P3", "score": 2,
                            "description": "数据记录处理并分析误差来源",
                            "keywords": ["数据", "误差", "读数"]},
                       ]),
    ])
    db.commit()
    _seed_users(db, course)
    _seed_answers(db, items)
    return grade_seed_answers(db)


def ensure_seeded(db: Session) -> bool:
    """库空(无课程)则注入种子, 返回是否执行过."""
    if db.query(Course).count() == 0:
        seed_all(db)
        return True
    return False


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    init_db()
    db = SessionLocal()
    try:
        if reset:
            from app.db import Base, engine
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
        stats = seed_all(db)
        from app.models import Answer, Course, Item, KnowledgeNode, SkillDimension
        print("初始化示例数据就绪: "
              f"{db.query(Course).count()} 门课程 / {db.query(KnowledgeNode).count()} 个知识节点 / "
              f"{db.query(SkillDimension).count()} 个能力维度 / {db.query(Item).count()} 道题目 / "
              f"{db.query(Answer).count()} 份答卷已写入。")
        print(f"种子评阅统计: {stats}")
    finally:
        db.close()
