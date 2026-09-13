"""端到端智能测试 v2：语义槽评分算法优化前后对比.

v1 问题复盘(2026-09-13):
- 原引擎 coverage_ratio = 命中去重字符数 / 全部关键字字符总长
- 同义变体越多, 分母越大; 学生只写一种写法时命中占比低, 强档答案被判半分
- 结果: 引擎 88.9% 一致率, 强档仅 67%, T1 强档引擎 5.0 vs 教师 8.0

v2 优化:
1. 关键字优化: keywords 改为语义槽 slots(同义变体分组), 每槽命中任一即算覆盖
2. 算法优化: 得分点覆盖度 = 命中槽数 / 总槽数, 得分 = 满分 × 覆盖度(支持半分/部分分)
3. 对比: 原引擎(字符覆盖率) vs 优化评分器(语义槽) vs 教师二审(语义槽+教师判断)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.engines.subjective import grade_subjective  # noqa: E402
from app.engines.base import EngineOutcome  # noqa: E402

# ============================================================
# 测试题目定义 v2: 语义槽结构
# slots: 每个得分点由若干语义槽组成, 槽内为同义变体, 命中任一即槽覆盖
# legacy_keywords: 保留 v1 的松散关键字列表, 用于原引擎对比
# ============================================================
TEST_ITEMS = [
    {
        "id": "T1",
        "type": "subjective_text",
        "title": "质量 m=2kg 的物体在水平面上受到 F=10N 的水平拉力，物体与地面间动摩擦因数 μ=0.2，取 g=10m/s²。求物体的加速度大小。",
        "max_score": 8.0,
        "reference_answer": (
            "由牛顿第二定律，物体所受合外力等于质量乘以加速度。"
            "竖直方向支持力 N=mg=20N；滑动摩擦力 f=μN=μmg=0.2×2×10=4N，方向与运动方向相反。"
            "水平方向合外力 F合=F-f=10-4=6N。"
            "由 F合=ma 得 a=F合/m=6/2=3m/s²。"
        ),
        # v1 松散关键字(原引擎用)
        "legacy_keywords": {
            "P1": ["牛顿第二定律", "F合=ma", "F=ma", "合外力等于", "ma"],
            "P2": ["摩擦力", "μmg", "μN", "0.2", "4N", "4 N"],
            "P3": ["合外力", "F-f", "10-4", "6N", "6 N"],
            "P4": ["加速度", "a=", "3m/s", "3 m/s", "6/2"],
        },
        # v2 语义槽(优化评分器用)
        "rubric": [
            {"point_id": "P1", "score": 2.0,
             "description": "写出牛顿第二定律及其公式关系",
             "slots": [
                 {"label": "定律名称", "keywords": ["牛顿第二定律", "牛二定律", "牛顿定律"]},
                 {"label": "公式关系", "keywords": ["F合=ma", "F=ma", "合外力等于质量乘以加速度", "ma", "a=F/m"]},
             ]},
            {"point_id": "P2", "score": 2.0,
             "description": "识别摩擦力并正确计算",
             "slots": [
                 {"label": "识别摩擦", "keywords": ["摩擦力", "滑动摩擦"]},
                 {"label": "摩擦计算", "keywords": ["μmg", "μN", "0.2×20", "0.2×2×10", "=4N", "4 N", "4牛"]},
             ]},
            {"point_id": "P3", "score": 2.0,
             "description": "正确计算合外力",
             "slots": [
                 {"label": "识别合外力", "keywords": ["合外力", "合力", "水平方向"]},
                 {"label": "合外力数值", "keywords": ["F-f", "10-4", "=6N", "6 N", "6牛"]},
             ]},
            {"point_id": "P4", "score": 2.0,
             "description": "正确计算加速度",
             "slots": [
                 {"label": "加速度形式", "keywords": ["加速度", "a=", "a ="]},
                 {"label": "加速度数值", "keywords": ["3m/s", "3 m/s", "3米每秒", "6/2"]},
             ]},
        ],
        "scoring_policy": {"review_threshold": 0.72},
    },
    {
        "id": "T2",
        "type": "subjective_text",
        "title": "简述什么是惯性，并说明惯性大小由什么决定，举一个生活中的例子。",
        "max_score": 6.0,
        "reference_answer": (
            "惯性是物体保持原有运动状态（静止或匀速直线运动）的性质，是物体的固有属性。"
            "惯性大小由物体的质量决定，质量越大惯性越大。"
            "生活例子：公交车急刹车时，乘客身体会向前倾，因为乘客由于惯性保持原来的运动状态。"
        ),
        "legacy_keywords": {
            "P1": ["惯性", "保持", "运动状态", "静止", "匀速", "固有属性"],
            "P2": ["质量", "决定", "越大", "质量大"],
            "P3": ["刹车", "前倾", "急刹", "拍打", "灰尘", "例子", "生活"],
        },
        "rubric": [
            {"point_id": "P1", "score": 2.0,
             "description": "正确表述惯性定义",
             "slots": [
                 {"label": "概念词", "keywords": ["惯性", "惯性是"]},
                 {"label": "保持性质", "keywords": ["保持", "维持", "运动状态", "静止", "匀速直线运动", "固有属性", "本身属性"]},
             ]},
            {"point_id": "P2", "score": 2.0,
             "description": "指出惯性大小由质量决定",
             "slots": [
                 {"label": "质量决定", "keywords": ["质量", "由质量"]},
                 {"label": "大小关系", "keywords": ["越大", "质量大", "决定", "有关"]},
             ]},
            {"point_id": "P3", "score": 2.0,
             "description": "举出合理生活例子",
             "slots": [
                 {"label": "生活场景", "keywords": ["刹车", "急刹", "公交", "汽车", "坐车", "拍打", "灰尘", "生活"]},
                 {"label": "惯性现象", "keywords": ["前倾", "往前倒", "向前", "例子", "比如", "例如"]},
             ]},
        ],
        "scoring_policy": {"review_threshold": 0.72},
    },
    {
        "id": "T3",
        "type": "spoken",
        "title": "请陈述动能定理的内容、公式并举一个应用例子。（文字模拟口语转写结果）",
        "max_score": 6.0,
        "reference_answer": (
            "动能定理：合外力对物体做的总功等于物体动能的变化量。"
            "公式 W总=ΔEk=½mv²−½mv₀²。"
            "例子：汽车刹车时，摩擦力做负功使汽车动能减小，最终停下来。"
        ),
        "legacy_keywords": {
            "P1": ["动能定理", "合外力", "做功", "动能变化", "总功"],
            "P2": ["W=", "ΔEk", "½mv²", "1/2mv", "动能变化", "公式"],
            "P3": ["刹车", "汽车", "摩擦", "例子", "应用", "停下来"],
        },
        "rubric": [
            {"point_id": "P1", "score": 2.0,
             "description": "正确表述动能定理内容",
             "slots": [
                 {"label": "定理名称", "keywords": ["动能定理"]},
                 {"label": "做功关系", "keywords": ["合外力", "做功", "总功", "动能变化", "动能的变化量", "等于"]},
             ]},
            {"point_id": "P2", "score": 2.0,
             "description": "写出动能定理公式",
             "slots": [
                 {"label": "公式形式", "keywords": ["W=", "W总", "ΔEk", "½mv", "1/2mv", "二分之一mv", "动能变化"]},
                 {"label": "公式要素", "keywords": ["初动能", "末动能", "初速度", "末速度", "mv", "v²", "平方"]},
             ]},
            {"point_id": "P3", "score": 2.0,
             "description": "举出合理应用例子",
             "slots": [
                 {"label": "应用场景", "keywords": ["刹车", "汽车", "摩擦力", "摩擦", "应用", "例子", "比如"]},
                 {"label": "效果描述", "keywords": ["停下来", "停止", "减速", "动能减小", "做负功"]},
             ]},
        ],
        "scoring_policy": {"review_threshold": 0.72},
    },
]

# ============================================================
# 三档学生答案(强/中/弱)
# ============================================================
STUDENT_ANSWERS = {
    "T1": {
        "strong": (
            "根据牛顿第二定律 F合=ma。先求摩擦力：竖直方向 N=mg=2×10=20N，"
            "滑动摩擦力 f=μN=0.2×20=4N。水平方向合外力 F合=F-f=10-4=6N。"
            "所以加速度 a=F合/m=6/2=3m/s²。"
        ),
        "mid": (
            "用牛顿第二定律来做。摩擦力 f=μmg=0.2×2×10=4N。"
            "合力就是 10-4=6N。加速度 a=6/2=3m/s²。"
        ),
        "weak": (
            "F=ma，所以 a=F/m=10/2=5m/s²。"
        ),
    },
    "T2": {
        "strong": (
            "惯性是物体保持原来运动状态不变的性质，不管是静止还是匀速直线运动都有惯性，"
            "它是物体本身的固有属性。惯性的大小只由质量决定，质量大的物体惯性大。"
            "比如公交车急刹车的时候，乘客的脚跟着车停了，但身体由于惯性还保持向前运动，所以会向前倾。"
        ),
        "mid": (
            "惯性就是物体保持原来运动状态的性质。惯性大小和质量有关，质量越大惯性越大。"
            "比如坐车刹车时人会往前倒。"
        ),
        "weak": (
            "惯性就是一种力，让物体动起来。比如推桌子的时候桌子很重。"
        ),
    },
    "T3": {
        "strong": (
            "动能定理说的是合外力对物体做的总功等于物体动能的变化量。"
            "公式是 W总=ΔEk=½mv²减去½mv₀的平方。"
            "举个例子，汽车刹车的时候，地面的摩擦力对汽车做负功，汽车的动能就逐渐减小，最后减到零就停下来了。"
        ),
        "mid": (
            "动能定理就是合外力做功等于动能变化。公式是 W等于二分之一mv方减初动能。"
            "比如汽车刹车时摩擦力做功让车停下来。"
        ),
        "weak": (
            "动能定理就是动能等于二分之一mv平方。比如一个球滚得越快动能越大。"
        ),
    },
}


# ============================================================
# 评分器一: 原引擎(字符覆盖率, v1 关键字)
# ============================================================
def build_legacy_item(item: dict) -> dict:
    """把 v1 松散关键字转回 rubric 结构, 供原引擎评分."""
    legacy = item["legacy_keywords"]
    rubric = []
    for p in item["rubric"]:
        pid = p["point_id"]
        rubric.append({
            "point_id": pid,
            "score": p["score"],
            "description": p["description"],
            "keywords": legacy[pid],
        })
    return {
        "id": item["id"],
        "type": item["type"],
        "title": item["title"],
        "max_score": item["max_score"],
        "reference_answer": item["reference_answer"],
        "rubric": rubric,
        "scoring_policy": item["scoring_policy"],
    }


def grade_engine_original(item: dict, answer: str) -> dict:
    """原引擎评分(字符覆盖率)."""
    legacy_item = build_legacy_item(item)
    outcome: EngineOutcome = grade_subjective(legacy_item, answer)
    return {
        "total": round(outcome.total, 2),
        "point_results": {
            p.point_id: {"earned": p.earned, "status": p.status, "reason": p.reason}
            for p in outcome.point_results
        },
    }


# ============================================================
# 评分器二: 优化评分器(语义槽覆盖率, 已落地到引擎 grade_subjective)
# ============================================================
def slot_coverage(answer: str, slot: dict) -> bool:
    """语义槽覆盖: 槽内任一关键字命中即覆盖."""
    return any(kw in answer for kw in slot["keywords"])


def grade_optimized(item: dict, answer: str) -> dict:
    """调用真实引擎 grade_subjective, 传入语义槽 rubric(引擎已支持 slots).

    引擎内部: 覆盖度 = 命中槽数/总槽数, 得分 = 满分 × 覆盖度比例规则
    (ratio>=0.8 满分, >=0.4 半分, 否则 0 分)
    """
    outcome: EngineOutcome = grade_subjective(item, answer)
    return {
        "total": round(outcome.total, 2),
        "max_score": item["max_score"],
        "point_results": [
            {"point_id": p.point_id, "description": p.description,
             "max_score": p.max, "earned": p.earned, "status": p.status,
             "reason": p.reason}
            for p in outcome.point_results
        ],
    }


# ============================================================
# 评分器三: 教师二审(语义槽 + 教师判断)
# 教师对"表述完整但非标准措辞"更宽容: 槽内命中即算, 且对覆盖度取整到0.5档
# ============================================================
def teacher_grade(item: dict, answer: str) -> dict:
    """教师二审: 语义槽覆盖 + 教师宽松取分规则.

    - 全槽命中 → 满分
    - 命中一半及以上 → 取 0.5×满分 或按比例(教师对部分表述宽容, 高覆盖给高分)
    - 少于一半 → 0 分
    教师认为"槽命中=知识到位", 不因措辞差异扣分, 但表述不完整会降档.
    """
    rubric = item["rubric"]
    point_results = []
    total = 0.0
    for p in rubric:
        score = float(p["score"])
        slots = p.get("slots", [])
        if not slots:
            earned = score
            verdict = "satisfied"
            reason = "无语义槽, 默认满分"
        else:
            hit_count = sum(1 for s in slots if slot_coverage(answer, s))
            ratio = hit_count / len(slots)
            if ratio >= 1.0:
                earned = score
                verdict = "satisfied"
            elif ratio >= 0.5:
                # 教师宽容: 命中一半以上给 0.75 比例(高于机械按比例)
                earned = score * 0.75
                verdict = "partial"
            else:
                earned = 0.0
                verdict = "unsatisfied"
            reason = f"教师判定: 语义槽覆盖 {hit_count}/{len(slots)} ({ratio:.0%}), {verdict}"
        total += earned
        point_results.append({
            "point_id": p["point_id"],
            "description": p["description"],
            "max_score": score,
            "earned": round(earned, 2),
            "verdict": verdict,
            "reason": reason,
        })
    return {
        "total": round(total, 2),
        "max_score": item["max_score"],
        "point_results": point_results,
    }


# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 76)
    print("端到端智能测试 v2: 语义槽评分算法优化前后对比")
    print("=" * 76)
    print(f"题目数: {len(TEST_ITEMS)} | 三档答案 | 总答卷数: {len(TEST_ITEMS)*3}")
    print("对比: 原引擎(字符覆盖率) vs 优化评分器(语义槽) vs 教师二审(语义槽+教师判断)")
    print()

    all_results = []

    for item in TEST_ITEMS:
        print(f"\n{'='*76}")
        print(f"题目 {item['id']}: {item['title'][:55]}...")
        print(f"满分: {item['max_score']} | 得分点: {len(item['rubric'])}")
        for p in item["rubric"]:
            slots_desc = " / ".join(f"{s['label']}[{len(s['keywords'])}变体]" for s in p["slots"])
            print(f"  {p['point_id']}({p['score']}分): {slots_desc}")
        print(f"{'='*76}")

        for level in ["strong", "mid", "weak"]:
            answer = STUDENT_ANSWERS[item["id"]][level]
            print(f"\n--- [{level.upper()}] ---")
            print(f"  答案: {answer[:80]}{'...' if len(answer) > 80 else ''}")

            # 原引擎
            orig = grade_engine_original(item, answer)
            # 优化评分器
            opt = grade_optimized(item, answer)
            # 教师二审
            teach = teacher_grade(item, answer)

            # 对比
            diff_opt = round(abs(opt["total"] - teach["total"]), 2)
            within_1_opt = diff_opt <= 1.0
            diff_orig = round(abs(orig["total"] - teach["total"]), 2)
            within_1_orig = diff_orig <= 1.0

            print(f"  原引擎 : {orig['total']}/{item['max_score']}")
            print(f"  优化后 : {opt['total']}/{item['max_score']}")
            print(f"  教师二审: {teach['total']}/{item['max_score']}")
            print(f"  优化vs教师: 分差{diff_opt} {'✓一致' if within_1_opt else '✗不一致'} | "
                  f"原引擎vs教师: 分差{diff_orig} {'✓一致' if within_1_orig else '✗不一致'}")

            # 逐得分点
            print(f"  逐得分点:")
            opt_points_map = {p["point_id"]: p for p in opt["point_results"]}
            for tp in teach["point_results"]:
                pid = tp["point_id"]
                op = opt_points_map.get(pid, {})
                op_earned = op.get("earned", "N/A")
                print(f"    {pid}: 优化={op_earned}/{tp['max_score']} | 教师={tp['earned']}/{tp['max_score']}({tp['verdict']}) | {tp['reason']}")

            all_results.append({
                "item_id": item["id"],
                "level": level,
                "answer": answer,
                "engine_original_score": orig["total"],
                "engine_optimized_score": opt["total"],
                "teacher_score": teach["total"],
                "diff_optimized_vs_teacher": diff_opt,
                "within_1_optimized": within_1_opt,
                "diff_original_vs_teacher": diff_orig,
                "within_1_original": within_1_orig,
                "optimized_points": {p["point_id"]: p for p in opt["point_results"]},
                "teacher_points": teach["point_results"],
            })

    # ============================================================
    # 汇总统计
    # ============================================================
    n = len(all_results)

    def summarize(key_within, key_diff):
        c = sum(1 for r in all_results if r[key_within])
        d = sum(r[key_diff] for r in all_results) / n
        return c, d

    orig_c, orig_d = summarize("within_1_original", "diff_original_vs_teacher")
    opt_c, opt_d = summarize("within_1_optimized", "diff_optimized_vs_teacher")

    print("\n" + "=" * 76)
    print("汇总统计(以教师二审为基准)")
    print("=" * 76)
    print(f"总答卷数: {n}")
    print(f"原引擎  : ±1分一致 {orig_c}/{n} ({orig_c/n:.1%}), 平均绝对分差 {orig_d:.2f}")
    print(f"优化后  : ±1分一致 {opt_c}/{n} ({opt_c/n:.1%}), 平均绝对分差 {opt_d:.2f}")
    print(f"提升    : 一致率 +{(opt_c-orig_c)/n:.1%}, 平均分差 {orig_d-opt_d:+.2f}")

    # 按档位
    print("\n按档位(优化后):")
    for level in ["strong", "mid", "weak"]:
        lr = [r for r in all_results if r["level"] == level]
        ln = len(lr)
        lc = sum(1 for r in lr if r["within_1_optimized"])
        ld = sum(r["diff_optimized_vs_teacher"] for r in lr) / ln
        print(f"  {level.upper()}: {lc}/{ln} ({lc/ln:.0%}), 平均分差 {ld:.2f}")

    # 按题目
    print("\n按题目(优化后):")
    for item in TEST_ITEMS:
        ir = [r for r in all_results if r["item_id"] == item["id"]]
        inn = len(ir)
        ic = sum(1 for r in ir if r["within_1_optimized"])
        print(f"  {item['id']}: {ic}/{inn} ({ic/inn:.0%})")

    # 保存报告
    report = {
        "version": "v2",
        "date": "2026-09-13",
        "test_design": {
            "method": "语义槽评分算法优化前后对比",
            "optimization": [
                "关键字优化: 松散keywords改为语义槽slots(同义变体分组, 命中任一即槽覆盖)",
                "算法优化: 覆盖度=命中槽数/总槽数, 消除同义变体膨胀分母缺陷",
                "教师二审: 语义槽+教师宽容取分(50%以上覆盖给0.75比例)",
            ],
            "note": "教师二审为标准答案关键字对照模拟, 非真实教师评分; 仅适用于基础低开放性题目",
        },
        "summary": {
            "total": n,
            "original_consistency_rate": round(orig_c / n, 4),
            "original_avg_abs_diff": round(orig_d, 4),
            "optimized_consistency_rate": round(opt_c / n, 4),
            "optimized_avg_abs_diff": round(opt_d, 4),
            "improvement_rate": round((opt_c - orig_c) / n, 4),
        },
        "details": all_results,
    }
    report_path = Path(__file__).parent / "simulated_teacher_test_report_v2.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详细报告已写入: {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
