"""端到端多模态评阅验证: OCR 文本 / ASR 转写 -> 引擎判分.

对真实学生素材(2张图片作答 + 4段语音 + 1个视频)的识别/转写结果,
用语义槽量规调用真实引擎 grade_subjective 判分, 验证多模态全链路。

用法:
    cd backend
    .venv\\Scripts\\python ..\\scripts\\e2e_multimodal_eval.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.engines.subjective import grade_subjective  # noqa: E402

HERE = Path(__file__).parent
OCR_RESULTS = HERE / "ocr_eval" / "results" / "ocr_report.json"
ASR_RESULTS = HERE / "asr_eval" / "results" / "asr_report.json"

# 语义槽量规(与 teacher_sim 一致, 适配真实作答文本)
# 题1: 受力分析求加速度 (满分8, 4得分点)
Q1_ITEM = {
    "title": "质量 m=3kg 的物体静止在水平面上，受到水平拉力 F=15N，动摩擦因数 μ=0.1，g=10m/s²。求加速度。",
    "rubric": [
        {"point_id": "P1", "description": "定律名称/公式关系", "score": 2,
         "slots": [
             {"label": "定律名称", "keywords": ["牛顿第二定律", "牛顿定律", "第二定律", "F=ma", "F合=ma", "a=F/m"]},
             {"label": "公式关系", "keywords": ["合外力", "合力", "F合", "ma", "质量与加速度"]},
         ]},
        {"point_id": "P2", "description": "识别摩擦力并计算", "score": 2,
         "slots": [
             {"label": "识别摩擦", "keywords": ["摩擦力", "滑动摩擦", "f=μN", "μN"]},
             {"label": "摩擦计算", "keywords": ["0.1×30", "0.1*30", "3N", "=3", "f=3"]},
         ]},
        {"point_id": "P3", "description": "识别合外力并计算", "score": 2,
         "slots": [
             {"label": "识别合外力", "keywords": ["F-f", "F合", "合外力", "合力"]},
             {"label": "合外力数值", "keywords": ["15-3", "12N", "=12"]},
         ]},
        {"point_id": "P4", "description": "加速度公式与数值", "score": 2,
         "slots": [
             {"label": "加速度形式", "keywords": ["a=F/m", "a=(F-f)/m", "aF", "F合/m", "a=12/3", "4m/s", "4 m/s"]},
             {"label": "加速度数值", "keywords": ["4m/s", "4 m/s", "=4", "4米"]},
         ]},
    ],
    "max_score": 8,
}

# 题2: 机械能守恒定律 (满分6, 3得分点)
Q2_ITEM = {
    "title": "简述机械能守恒定律的内容，并写出其公式。",
    "rubric": [
        {"point_id": "P1", "description": "定律名称/条件", "score": 2,
         "slots": [
             {"label": "定律名称", "keywords": ["机械能守恒", "机械能守恒定律"]},
             {"label": "适用条件", "keywords": ["只有重力", "弹力做功", "重力或弹力", "没有摩擦", "只受重力"]},
         ]},
        {"point_id": "P2", "description": "内容表述", "score": 2,
         "slots": [
             {"label": "守恒表述", "keywords": ["机械能保持不变", "机械能不变", "守恒", "保持不变", "动能和势能", "动能与势能"]},
             {"label": "转化关系", "keywords": ["相互转化", "可以转化", "互相转化", "转换"]},
         ]},
        {"point_id": "P3", "description": "公式", "score": 2,
         "slots": [
             {"label": "公式形式", "keywords": ["Ek1+Ep1=Ek2+Ep2", "Ek1+Ep1", "Ek2+Ep2", "E1=E2", "E初=E末", "Ek+Ep"]},
             {"label": "公式要素", "keywords": ["Ek", "Ep", "动能", "势能", "ΔEk=-ΔEp", "ΔEk", "ΔEp"]},
         ]},
    ],
    "max_score": 6,
}

# 语音题1: 牛顿第三定律 (满分6, 3得分点)
VOICE1_ITEM = {
    "title": "请讲清牛顿第三定律的内容，并举一个生活中的例子。",
    "rubric": [
        {"point_id": "P1", "description": "定律名称", "score": 2,
         "slots": [
             {"label": "定律名称", "keywords": ["牛顿第三定律", "第三定律", "作用力和反作用力", "反作用力"]},
             {"label": "大小关系", "keywords": ["大小相等", "大小总是相等", "大小相等方向相反", "相等"]},
         ]},
        {"point_id": "P2", "description": "方向/对象", "score": 2,
         "slots": [
             {"label": "方向相反", "keywords": ["方向相反", "相反", "作用在同一直线上", "同一条直线"]},
             {"label": "作用对象", "keywords": ["两个不同物体", "两个物体", "不同物体", "分别作用"]},
         ]},
        {"point_id": "P3", "description": "生活例子", "score": 2,
         "slots": [
             {"label": "例子", "keywords": ["推墙", "划船", "走路", "火箭", "我推", "推桌", "气球", "滑冰", "作用"]},
             {"label": "例子说明", "keywords": ["也推我", "水对桨", "反作用力", "向前", "后退", "同时"]},
         ]},
    ],
    "max_score": 6,
}

# 语音题2: 动能 (满分6, 3得分点)
VOICE2_ITEM = {
    "title": "请说明什么是动能，写出动能公式，并举例说明动能大小与哪些因素有关。",
    "rubric": [
        {"point_id": "P1", "description": "动能概念", "score": 2,
         "slots": [
             {"label": "动能概念", "keywords": ["运动而具有", "运动具有", "运动均有的能量", "由于运动", "动能"]},
             {"label": "能量性质", "keywords": ["能量", "动能"]},
         ]},
        {"point_id": "P2", "description": "公式", "score": 2,
         "slots": [
             {"label": "公式形式", "keywords": ["二分之一mv", "1/2mv", "½mv", "EK", "Ek", "1K", "E等于"]},
             {"label": "公式要素", "keywords": ["质量", "速度", "平方", "v方", "V的平方", "m乘"]},
         ]},
        {"point_id": "P3", "description": "因素与例子", "score": 2,
         "slots": [
             {"label": "影响因素", "keywords": ["质量", "速度", "质量和速度", "质量与速度"]},
             {"label": "例子", "keywords": ["小车", "卡车", "汽车", "刹车", "跑得快", "速度越大"]},
         ]},
    ],
    "max_score": 6,
}

# 视频题: 弹簧测力计测重力 (满分6, 3得分点)
VIDEO_ITEM = {
    "title": "演示并讲解用弹簧测力计测量物体重力的实验过程。",
    "rubric": [
        {"point_id": "P1", "description": "实验准备(调零)", "score": 2,
         "slots": [
             {"label": "调零", "keywords": ["调零", "调室", "零刻度", "指针对准", "校零"]},
             {"label": "检查", "keywords": ["自然下垂", "测量范围", "量程", "估测", "超过"]},
         ]},
        {"point_id": "P2", "description": "测量操作", "score": 2,
         "slots": [
             {"label": "挂物", "keywords": ["挂", "挂钩", "物体挂", "悬挂"]},
             {"label": "读数", "keywords": ["平视", "读数", "读书", "指针稳定", "稳定后", "视线"]},
         ]},
        {"point_id": "P3", "description": "原理与记录", "score": 2,
         "slots": [
             {"label": "原理", "keywords": ["重力", "二力平衡", "拉力等于", "弹簧", "示数", "刻度"]},
             {"label": "记录", "keywords": ["记录", "数据", "结果", "重力值"]},
         ]},
    ],
    "max_score": 6,
}


def grade_text(item: dict, text: str) -> dict:
    """调用真实引擎判分(语义槽)."""
    outcome = grade_subjective(item, text or "", llm=None, quality={})
    return {
        "total": round(outcome.total, 2),
        "max": item["max_score"],
        "points": [
            {"id": p.point_id, "earned": p.earned, "max": p.max,
             "status": p.status, "reason": p.reason}
            for p in outcome.point_results
        ],
    }


def main():
    print("=" * 70)
    print("端到端多模态评阅验证 (OCR/ASR -> 引擎判分)")
    print("=" * 70)

    # ---- 加载 OCR 结果 ----
    ocr = json.loads(OCR_RESULTS.read_text(encoding="utf-8"))
    # ---- 加载 ASR 结果 ----
    asr = json.loads(ASR_RESULTS.read_text(encoding="utf-8"))

    report = {"ocr": {}, "asr": {}, "video": {}}

    # ---- 图片作答 -> OCR -> 判分 ----
    print("\n【图片作答 OCR -> 判分】")
    # 同学1: student1_q1 -> 题1, student1_q2 -> 题2
    # 同学2: student2_q1 -> 题1, student2_q2 -> 题2
    img_cases = [
        ("同学1(70分) 题1", "student1_q1", Q1_ITEM),
        ("同学1(70分) 题2", "student1_q2", Q2_ITEM),
        ("同学2(90分) 题1", "student2_q1", Q1_ITEM),
        ("同学2(90分) 题2", "student2_q2", Q2_ITEM),
    ]
    for label, key, item in img_cases:
        rec = ocr.get(key)
        if not rec or rec.get("status") != "ok":
            print(f"  {label}: [无 OCR 结果]")
            continue
        text = rec["text"]
        result = grade_text(item, text)
        print(f"  {label}: {result['total']}/{result['max']} 分 (OCR {len(text)}字)")
        for p in result["points"]:
            print(f"    {p['id']}: {p['earned']}/{p['max']} [{p['status']}] {p['reason'][:70]}")
        report["ocr"][key] = {"label": label, "total": result["total"],
                              "max": result["max"], "points": result["points"],
                              "text": text}

    # ---- 语音作答 -> ASR -> 判分 ----
    print("\n【语音作答 ASR -> 判分】")
    voice_cases = [
        ("同学1(70分) 录音1 牛顿第三定律", "采访录音 1", VOICE1_ITEM),
        ("同学1(70分) 录音2 动能", "采访录音 2", VOICE2_ITEM),
        ("同学2(90分) 录音3 牛顿第三定律", "采访录音 3", VOICE1_ITEM),
        ("同学2(90分) 录音4 动能", "采访录音 4", VOICE2_ITEM),
    ]
    for label, key, item in voice_cases:
        rec = asr.get(key)
        if not rec or rec.get("status") != "ok":
            print(f"  {label}: [无 ASR 结果]")
            continue
        text = rec["text"]
        result = grade_text(item, text)
        dur = rec.get("duration_ms", 0) / 1000
        print(f"  {label}: {result['total']}/{result['max']} 分 (ASR {len(text)}字, {dur:.1f}s)")
        for p in result["points"]:
            print(f"    {p['id']}: {p['earned']}/{p['max']} [{p['status']}] {p['reason'][:70]}")
        report["asr"][key] = {"label": label, "total": result["total"],
                              "max": result["max"], "points": result["points"],
                              "text": text}

    # ---- 视频作答 -> 音轨转写 -> 判分 ----
    print("\n【视频作答 音轨转写 -> 判分】")
    vkey = "题5"
    rec = asr.get(vkey)
    if rec and rec.get("status") == "ok":
        text = rec["text"]
        result = grade_text(VIDEO_ITEM, text)
        dur = rec.get("duration_ms", 0) / 1000
        print(f"  题5 弹簧测力计实验: {result['total']}/{result['max']} 分 (转写 {len(text)}字, {dur:.1f}s)")
        for p in result["points"]:
            print(f"    {p['id']}: {p['earned']}/{p['max']} [{p['status']}] {p['reason'][:70]}")
        report["video"]["题5"] = {"total": result["total"], "max": result["max"],
                                  "points": result["points"], "text": text}
    else:
        print("  [无视频转写结果]")

    out = HERE / "e2e_multimodal_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完整报告已写入: {out}")


if __name__ == "__main__":
    main()
