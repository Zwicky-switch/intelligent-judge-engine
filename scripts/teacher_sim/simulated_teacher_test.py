"""端到端智能测试：引擎判分 vs 关键字对照法教师二审.

测试设计:
- 3 道基础低开放性题目(2 道主观文本 + 1 道口语文字模拟)
- 每道题 3 档学生答案(强/中/弱), 共 9 份答卷
- 引擎: 调用 grade_subjective 本地内置引擎判分
- 教师二审: 标准答案关键字对照法, 逐得分点判定
- 输出: 逐题逐得分点对比 + 一致率(±1分) + 平均绝对差
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
# 测试题目定义(模仿数据库已有题目的量规结构)
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
        "rubric": [
            {"point_id": "P1", "score": 2.0,
             "description": "写出牛顿第二定律 F合=ma 或等价表述",
             "keywords": ["牛顿第二定律", "F合=ma", "F=ma", "合外力等于", "ma"]},
            {"point_id": "P2", "score": 2.0,
             "description": "正确计算摩擦力 f=μmg=4N",
             "keywords": ["摩擦力", "μmg", "μN", "0.2", "4N", "4 N"]},
            {"point_id": "P3", "score": 2.0,
             "description": "正确计算合外力 F合=F-f=6N",
             "keywords": ["合外力", "F-f", "10-4", "6N", "6 N"]},
            {"point_id": "P4", "score": 2.0,
             "description": "正确计算加速度 a=3m/s²",
             "keywords": ["加速度", "a=", "3m/s", "3 m/s", "6/2"]},
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
        "rubric": [
            {"point_id": "P1", "score": 2.0,
             "description": "正确表述惯性定义（保持原有运动状态的性质）",
             "keywords": ["惯性", "保持", "运动状态", "静止", "匀速", "固有属性"]},
            {"point_id": "P2", "score": 2.0,
             "description": "指出惯性大小由质量决定",
             "keywords": ["质量", "决定", "越大", "质量大"]},
            {"point_id": "P3", "score": 2.0,
             "description": "举出合理的生活例子（如刹车前倾、拍打灰尘等）",
             "keywords": ["刹车", "前倾", "急刹", "拍打", "灰尘", "例子", "生活"]},
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
        "rubric": [
            {"point_id": "P1", "score": 2.0,
             "description": "正确表述动能定理内容（合外力做功等于动能变化）",
             "keywords": ["动能定理", "合外力", "做功", "动能变化", "总功"]},
            {"point_id": "P2", "score": 2.0,
             "description": "写出公式 W=ΔEk 或 ½mv²−½mv₀²",
             "keywords": ["W=", "ΔEk", "½mv²", "1/2mv", "动能变化", "公式"]},
            {"point_id": "P3", "score": 2.0,
             "description": "举出合理应用例子",
             "keywords": ["刹车", "汽车", "摩擦", "例子", "应用", "停下来"]},
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
# 教师二审: 关键字对照法
# ============================================================
def teacher_grade(item: dict, answer_text: str) -> dict:
    """用标准答案关键字对照法模拟教师二审评分.

    规则:
    - 每个得分点: 命中 >=60% 关键字 → 满分; 命中 >=30% → 半分; 否则 0 分
    - 与引擎的覆盖率阈值(0.8/0.4)略有不同, 模拟教师的宽松度
    """
    rubric = item["rubric"]
    point_results = []
    total = 0.0
    for p in rubric:
        keywords = p.get("keywords", [])
        score = float(p["score"])
        if not keywords:
            earned = score
            verdict = "satisfied"
            reason = "无关键字, 默认满分"
        else:
            matched = [k for k in keywords if k in answer_text]
            ratio = len(matched) / len(keywords)
            if ratio >= 0.6:
                earned = score
                verdict = "satisfied"
                reason = f"教师判定: 关键字覆盖{ratio:.0%}, 满分"
            elif ratio >= 0.3:
                earned = score * 0.5
                verdict = "partial"
                reason = f"教师判定: 关键字覆盖{ratio:.0%}, 半分"
            else:
                earned = 0.0
                verdict = "unsatisfied"
                reason = f"教师判定: 关键字覆盖{ratio:.0%}, 不得分"
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
# 主测试流程
# ============================================================
def main():
    print("=" * 70)
    print("端到端智能测试: 引擎判分 vs 关键字对照法教师二审")
    print("=" * 70)
    print(f"题目数: {len(TEST_ITEMS)} | 每档答案: 强/中/弱 | 总答卷数: {len(TEST_ITEMS)*3}")
    print()

    all_results = []
    engine_scores = []
    teacher_scores = []

    for item in TEST_ITEMS:
        print(f"\n{'='*70}")
        print(f"题目 {item['id']}: {item['title'][:60]}...")
        print(f"满分: {item['max_score']} | 得分点: {len(item['rubric'])}")
        print(f"{'='*70}")

        for level in ["strong", "mid", "weak"]:
            answer = STUDENT_ANSWERS[item["id"]][level]
            print(f"\n--- [{level.upper()}] 学生答案 ---")
            print(f"  {answer[:100]}{'...' if len(answer) > 100 else ''}")

            # 引擎判分
            outcome: EngineOutcome = grade_subjective(item, answer)
            engine_total = round(outcome.total, 2)
            engine_conf = outcome.confidence
            engine_review = outcome.review_level

            # 教师二审
            teacher = teacher_grade(item, answer)
            teacher_total = teacher["total"]

            # 对比
            diff = round(abs(engine_total - teacher_total), 2)
            within_1 = diff <= 1.0

            print(f"  引擎判分: {engine_total}/{item['max_score']} (置信度={engine_conf}, 复核档={engine_review})")
            print(f"  教师二审: {teacher_total}/{item['max_score']}")
            print(f"  分差: {diff} | ±1分内一致: {'是' if within_1 else '否'}")

            # 逐得分点对比
            print(f"  逐得分点对比:")
            eng_points = {p.point_id: p for p in outcome.point_results}
            for tp in teacher["point_results"]:
                pid = tp["point_id"]
                ep = eng_points.get(pid)
                ep_earned = ep.earned if ep else "N/A"
                ep_status = ep.status if ep else "N/A"
                print(f"    {pid}: 引擎={ep_earned}/{tp['max_score']}({ep_status}) | "
                      f"教师={tp['earned']}/{tp['max_score']}({tp['verdict']})")

            engine_scores.append(engine_total)
            teacher_scores.append(teacher_total)
            all_results.append({
                "item_id": item["id"],
                "item_title": item["title"],
                "level": level,
                "answer": answer,
                "engine_score": engine_total,
                "engine_confidence": engine_conf,
                "engine_review_level": engine_review,
                "engine_point_results": [
                    {"point_id": p.point_id, "earned": p.earned, "status": p.status, "reason": p.reason}
                    for p in outcome.point_results
                ],
                "teacher_score": teacher_total,
                "teacher_point_results": teacher["point_results"],
                "diff": diff,
                "within_1": within_1,
            })

    # ============================================================
    # 汇总统计
    # ============================================================
    print("\n" + "=" * 70)
    print("汇总统计")
    print("=" * 70)

    n = len(all_results)
    consistent = sum(1 for r in all_results if r["within_1"])
    avg_diff = sum(r["diff"] for r in all_results) / n
    consistency_rate = consistent / n

    print(f"总答卷数: {n}")
    print(f"±1分内一致数: {consistent}/{n} = {consistency_rate:.1%}")
    print(f"平均绝对分差: {avg_diff:.2f}")
    print(f"引擎平均分: {sum(engine_scores)/n:.2f}")
    print(f"教师平均分: {sum(teacher_scores)/n:.2f}")

    # 按档位统计
    print("\n按档位统计:")
    for level in ["strong", "mid", "weak"]:
        level_results = [r for r in all_results if r["level"] == level]
        ln = len(level_results)
        lc = sum(1 for r in level_results if r["within_1"])
        ld = sum(r["diff"] for r in level_results) / ln
        print(f"  {level.upper()}: {lc}/{ln} 一致 ({lc/ln:.0%}), 平均分差 {ld:.2f}")

    # 按题目统计
    print("\n按题目统计:")
    for item in TEST_ITEMS:
        item_results = [r for r in all_results if r["item_id"] == item["id"]]
        inn = len(item_results)
        inc = sum(1 for r in item_results if r["within_1"])
        ind = sum(r["diff"] for r in item_results) / inn
        print(f"  {item['id']}: {inc}/{inn} 一致 ({inc/inn:.0%}), 平均分差 {ind:.2f}")

    # 保存报告
    report = {
        "test_design": {
            "method": "引擎判分 vs 关键字对照法教师二审",
            "note": "教师二审为标准答案关键字对照模拟, 非真实教师评分; 适用于基础低开放性题目",
            "item_count": len(TEST_ITEMS),
            "answer_count": n,
            "levels": ["strong", "mid", "weak"],
        },
        "summary": {
            "total": n,
            "consistent_within_1": consistent,
            "consistency_rate": round(consistency_rate, 4),
            "avg_abs_diff": round(avg_diff, 4),
            "engine_avg": round(sum(engine_scores)/n, 4),
            "teacher_avg": round(sum(teacher_scores)/n, 4),
        },
        "details": all_results,
    }

    report_path = Path(__file__).parent / "simulated_teacher_test_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详细报告已写入: {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
