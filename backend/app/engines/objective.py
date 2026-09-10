"""客观题确定性判分引擎.

覆盖: 单选 / 多选 / 判断 / 填空 / 数值。
设计: 纯函数 + 幂等; 判分可解释(每道题输出 reason); 异常样例不静默判零。
准确率目标 100% —— 由 tests/test_objective.py 的金标准表守护。
"""
from __future__ import annotations

import re

from app.engines.base import EngineOutcome, EvidenceHit, clamp_score
from app.engines.numeric import evaluate_numeric, normalize_text
from app.constants import (
    T_SINGLE_CHOICE, T_MULTIPLE_CHOICE, T_TRUE_FALSE, T_FILL_BLANK, T_NUMERIC,
    V_SATISFIED, V_PARTIAL, V_UNSATISFIED,
)

_LETTER_RE = re.compile(r"[A-Ha-h]")
_TF_MAP = {
    "T": True, "F": False,
    "对": True, "错": False, "正": True, "√": True, "×": False,
    "true": True, "false": False, "yes": True, "no": False,
}


def extract_letters(response: str) -> list[str]:
    """抽取作答中的选项字母(按出现顺序去重)."""
    return list(dict.fromkeys(_LETTER_RE.findall(str(response or ""))))


def normalize_choice(response: str) -> str:
    """单选题/判断题作答规范化: 去掉'答案/选项/ABC.'等噪声后取字母/对错."""
    s = str(response or "").strip()
    s = re.sub(r"[（(]?\s*单选题\s*[)）]?", "", s)
    s = re.sub(r"(答案|选择|选项|选)\s*[:：]?\s*", "", s)
    return s.strip()


def _letters_set(response: str) -> set[str]:
    return set(x.upper() for x in extract_letters(response))


def grade_single_choice(cfg: dict, response: str, max_score: float) -> EngineOutcome:
    correct = str((cfg.get("correct") or "")).upper()
    sel = _letters_set(response)
    if not sel:
        return _obj_outcome(0.0, max_score, "空答或未识别到选项", V_UNSATISFIED,
                            f"标准答案 {correct}")
    if sel == {correct}:
        return _obj_outcome(max_score, max_score, f"作答 {''.join(sorted(sel))} 与标准答案 {correct} 一致", V_SATISFIED, "")
    extra = ",".join(sorted(sel - {correct}))
    return _obj_outcome(0.0, max_score, f"作答含错误选项 {extra} (标准答案 {correct})", V_UNSATISFIED,
                        f"标准答案 {correct}")


def grade_multiple_choice(cfg: dict, response: str, max_score: float) -> EngineOutcome:
    correct = set(x.upper() for x in (cfg.get("correct") or []))
    sel = _letters_set(response)
    if not correct:
        return _obj_outcome(0.0, max_score, "题目未配置标准答案", V_UNSATISFIED, "")
    if not sel:
        return _obj_outcome(0.0, max_score, "空答", V_UNSATISFIED,
                            f"标准答案 {','.join(sorted(correct))}")
    mode = cfg.get("scoring_mode", "full")
    hit = sel & correct
    wrong = sel - correct
    if mode == "partial" and correct:
        # 部分得分: 选对得分, 选错按对等扣回; 不低于 0
        ratio = (len(hit) - len(wrong)) / len(correct)
        earned = clamp_score(max_score * max(0.0, ratio), 0.0, max_score)
    else:
        earned = max_score if (hit == correct and not wrong) else 0.0
    status = V_SATISFIED if earned >= max_score - 1e-9 else (V_PARTIAL if earned > 0 else V_UNSATISFIED)
    missing = sorted(correct - sel)
    reason = (
        f"全对: 标准答案 {','.join(sorted(correct))}" if status == V_SATISFIED
        else (f"部分正确(选对 {len(hit)} 项" + (f", 误选 {len(wrong)} 项" if wrong else "") + ")" if status == V_PARTIAL
              else f"不正确: 漏选 {','.join(missing) if missing else '-'}, 误选 {','.join(sorted(wrong)) if wrong else '-'}")
    )
    return _obj_outcome(earned, max_score, reason, status, f"标准答案 {','.join(sorted(correct))}")


def grade_true_false(cfg: dict, response: str, max_score: float) -> EngineOutcome:
    s = normalize_choice(response)
    if not s:
        return _obj_outcome(0.0, max_score, "空答或未识别对错", V_UNSATISFIED, "标准答案 已给出")
    key = s[:2].lower() if len(s) >= 2 else s
    ans = _TF_MAP.get(s[:2].lower()) or _TF_MAP.get(s[0])
    if ans is None and s.lower() in _TF_MAP:
        ans = _TF_MAP[s.lower()]
    correct = bool(cfg.get("correct"))
    if ans is None:
        return _obj_outcome(0.0, max_score, f"无法识别作答「{s}」", V_UNSATISFIED,
                            "正确" if correct else "错误")
    ok = ans == correct
    return _obj_outcome(max_score if ok else 0.0, max_score,
                        ("作答与标准一致" if ok else "作答与标准相反"),
                        V_SATISFIED if ok else V_UNSATISFIED,
                        "正确" if correct else "错误")


def _split_blanks(response: str, n_blanks: int) -> list[str]:
    s = str(response or "").strip()
    if n_blanks == 1:
        return [s] if s else []
    parts = re.split(r"[|；;，,、\n]+", s)
    # 去掉首尾噪声
    parts = [p.strip() for p in parts if p.strip()]
    return parts


def _blank_matches(blank: dict, given: str) -> bool:
    """空答案匹配: value 可为字符串或备选字符串列表; 支持 case_sensitive/pattern."""
    given = normalize_text(given)
    if not given:
        return False
    values = blank.get("value")
    if isinstance(values, str):
        values = [values]
    values = values or []
    case_sensitive = bool(blank.get("case_sensitive", False))
    for v in values:
        cand = normalize_text(v)
        if not case_sensitive:
            if given.lower() == cand.lower():
                return True
        elif given == cand:
            return True
    pat = blank.get("pattern")
    if pat:
        try:
            return re.fullmatch(pat, given) is not None
        except re.error:
            pass
    return False


def grade_fill_blank(cfg: dict, response: str, max_score: float) -> EngineOutcome:
    blanks = cfg.get("blanks") or []
    if not blanks:
        blanks = [{"value": cfg.get("value") or cfg.get("correct")}]
    n = len(blanks)
    order_matters = bool(cfg.get("order_matters", True))
    parts = _split_blanks(response, n)
    if not parts:
        return _fill_outcome(blanks, [], max_score, "空答")
    score_each = max_score / n if n else max_score

    matched_idx: set[int] = set()
    if len(parts) < n:
        parts = parts + [""] * (n - len(parts))
    extra = len(parts) - n
    parts = parts[:n]

    # 位置匹配
    for i, blank in enumerate(blanks):
        if _blank_matches(blank, parts[i]):
            matched_idx.add(i)

    # 顺序无关模式: 用未占用作答去补足未命中的空(贪心, 确定性)
    if not order_matters:
        used_parts = [i for i in range(n) if i in matched_idx]
        pool = [parts[i] for i in range(n) if i not in used_parts]
        for i in range(n):
            if i in matched_idx:
                continue
            for j, g in enumerate(pool):
                if g and _blank_matches(blanks[i], g):
                    matched_idx.add(i)
                    pool.pop(j)
                    break

    earned = score_each * len(matched_idx)
    details = []
    for i, blank in enumerate(blanks):
        tag = "对" if i in matched_idx else ("错" if parts[i] else "未填")
        details.append((f"第{i+1}空", tag))

    if earned >= max_score - 1e-9:
        status, reason = V_SATISFIED, "全部填空与标准答案一致"
    elif earned > 0:
        status = V_PARTIAL
        reason = "部分填空正确: " + "、".join(f"{k}{v}" for k, v in details if v == "对")
    else:
        status, reason = V_UNSATISFIED, "填空均不正确"
    if extra:
        reason += "(作答空数超出题目, 已按前 N 空判定)"
    return _fill_outcome(blanks, details, max_score, reason, earned, status)


def _fill_outcome(blanks, details, max_score, reason, earned=0.0, status=V_UNSATISFIED):
    ev = EvidenceHit(label=status, kind="fill_blank",
                     snippet=" / ".join(d[0] + ":" + d[1] for d in details))
    return EngineOutcome(
        total=round(earned, 2), max_score=max_score,
        point_results=[], penalties=[], hits=[ev],
        comment="", reasoning=reason, confidence=1.0,
    )


def _obj_outcome(earned: float, max_score: float, reason: str, status: str,
                 expected: str, error: str = "") -> EngineOutcome:
    hit = EvidenceHit(label=status, kind="objective", snippet=reason or "客观判分")
    return EngineOutcome(
        ok=not error, total=round(clamp_score(earned, 0.0, max_score), 2),
        max_score=max_score,
        point_results=[],
        hits=[hit],
        comment="",
        reasoning=reason or error,
        confidence=1.0,
        error=error,
        extra={"expected": expected},
    )


def grade_numeric(cfg: dict, response: str, max_score: float) -> EngineOutcome:
    res = evaluate_numeric(cfg, response)
    earned = max_score * res["earned"]
    ev = EvidenceHit(label=res["status"], kind="numeric",
                     snippet=res["reason"])
    # 无法解析(空答/前缀噪声/公式写法)或缺标准答案: 仍给确定性 0 分,
    # 但通过 error 字段交由 runner 转人工复核(不静默判零后自动放行)
    parse_failed = res["parsed_value"] is None
    return EngineOutcome(
        total=round(earned, 2), max_score=max_score, point_results=[],
        penalties=[], hits=[ev], comment="",
        reasoning=res["reason"], confidence=1.0,
        error=res["reason"] if parse_failed else "",
        extra={"expected": res.get("expected"),
               "parsed_value": res.get("parsed_value"),
               "unit": cfg.get("answer", {}).get("unit", "")},
    )


def grade_objective(item_type: str, answer_config: dict, response: str,
                    max_score: float, policy: dict | None = None) -> EngineOutcome:
    """客观题统一入口. 判分逻辑确定性; 异常返回 ok=False 且带 error."""
    cfg = dict(answer_config or {})
    if item_type == T_SINGLE_CHOICE:
        return grade_single_choice(cfg, response, max_score)
    if item_type == T_MULTIPLE_CHOICE:
        return grade_multiple_choice(cfg, response, max_score)
    if item_type == T_TRUE_FALSE:
        return grade_true_false(cfg, response, max_score)
    if item_type == T_FILL_BLANK:
        return grade_fill_blank(cfg, response, max_score)
    if item_type == T_NUMERIC:
        return grade_numeric(cfg, response, max_score)
    return EngineOutcome(ok=False, total=0.0, max_score=max_score,
                         error=f"未支持的客观题题型: {item_type}",
                         reasoning=f"未支持的客观题题型: {item_type}")
