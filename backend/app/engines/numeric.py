"""数值题解析与比对: 数值 + 单位(量纲族+倍率)换算 + 容差 + 有效数字.

确定性、纯函数、幂等; 异常样例返回可解释失败原因。
单位校验只对「已知量纲族」的单位执行(见 _UNIT_FAMILY);
复合单位(如 N·m^2/kg^2)不在表内时退化为"纯数值比对", 不做错误扣分。
"""
from __future__ import annotations

import re

# 单位符号 -> (量纲族, 换算到该族基准单位的倍率)
_UNIT_FAMILY: dict[str, tuple[str, float]] = {
    # 长度 (m)
    "m": ("len", 1.0), "cm": ("len", 1e-2), "mm": ("len", 1e-3),
    "km": ("len", 1e3), "um": ("len", 1e-6),
    # 时间 (s)
    "s": ("time", 1.0), "ms": ("time", 1e-3), "us": ("time", 1e-6),
    "min": ("time", 60.0), "h": ("time", 3600.0),
    # 质量 (kg)
    "kg": ("mass", 1.0), "g": ("mass", 1e-3), "mg": ("mass", 1e-6), "t": ("mass", 1e3),
    # 力 (N)
    "n": ("force", 1.0), "kn": ("force", 1e3),
    # 能量 (J)
    "j": ("energy", 1.0), "kj": ("energy", 1e3),
    # 功率 (W)
    "w": ("power", 1.0), "kw": ("power", 1e3),
    # 速度 (m/s)
    "m/s": ("speed", 1.0), "km/h": ("speed", 1.0 / 3.6),
    # 加速度 (m/s^2)
    "m/s^2": ("acc", 1.0),
}

_ALIASES = {
    "米": "m", "厘米": "cm", "毫米": "mm", "千米": "km", "公里/小时": "km/h",
    "秒": "s", "分钟": "min", "小时": "h", "千克": "kg", "克": "g", "毫克": "mg",
    "牛": "n", "牛顿": "n", "千牛": "kn", "焦": "j", "焦耳": "j", "千焦": "kj",
    "瓦": "w", "瓦特": "w", "千瓦": "kw",
    "米每秒": "m/s", "米/秒": "m/s", "米每秒平方": "m/s^2",
    "米每二次方秒": "m/s^2", "米/秒^2": "m/s^2",
    "μm": "um", "µs": "us", "微米": "um", "毫秒": "ms", "微秒": "us",
}

_NUM_RE = re.compile(
    r"^\s*(?P<num>[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)"
    r"(?P<rest>.*)$"
)


def normalize_text(s: str) -> str:
    """去空白与噪声(用于填空等对齐比较)."""
    return re.sub(r"\s+", "", str(s or ""))


def clean_unit(unit: str) -> str:
    u = (unit or "").strip().lower().replace("²", "^2").replace("^ 2", "^2")
    u = u.replace("·", " ").strip()
    return _ALIASES.get(u, u)


def unit_info(unit: str) -> tuple[str, float] | None:
    """返回 (量纲族, 倍率); 未知/复合单位返回 None."""
    return _UNIT_FAMILY.get(clean_unit(unit))


def parse_numeric_answer(text: str) -> tuple[float | None, str, str]:
    """解析作答 -> (数值, 原单位串, 错误原因)."""
    s = str(text or "").strip()
    if not s:
        return None, "", "空答"
    m = _NUM_RE.match(s)
    if not m:
        return None, "", "作答无法解析为数值(含公式/图的内容建议改为主观题型)"
    try:
        value = float(m.group("num"))
    except ValueError:
        return None, "", "数值格式非法"
    rest = m.group("rest").strip()
    return value, rest, ""


def count_significant_digits(x: float | str) -> int:
    s = str(x).lower()
    if "e" in s:
        mant = s.split("e")[0]
        digits = "".join(ch for ch in mant if ch.isdigit())
        digits = digits.lstrip("0")
        return len(digits) if digits else 0
    s_norm = s.replace("-", "")
    if "." in s_norm:
        int_part, frac = s_norm.split(".", 1)
        core_int = int_part.lstrip("0")
        if core_int == "":
            frac_core = frac.lstrip("0")
            return len(frac_core) if frac_core else 0
        return len(core_int) + len(frac)
    core = s_norm.lstrip("0")
    return len(core.rstrip("0")) if core else 0


def sigfigs_of(value_text: str) -> int | None:
    m = _NUM_RE.match(str(value_text or "").strip())
    if not m:
        return None
    return count_significant_digits(m.group("num"))


def compare_with_tolerance(student_value: float, key_value: float, *,
                           tol_abs: float | None = None,
                           tol_rel: float | None = None) -> bool:
    diff = abs(student_value - key_value)
    if tol_abs is not None and diff <= tol_abs:
        return True
    if tol_rel is not None and abs(key_value) > 1e-300 and diff <= tol_rel * abs(key_value):
        return True
    # 无显式容差时的浮点噪声兜底(与数值量级成比例, 避免误吞大误差)
    return diff <= max(abs(key_value) * 1e-12, 1e-300)


def evaluate_numeric(config: dict, response_text: str) -> dict:
    """数值题评判. 返回 {correct, earned(0-1), status, reason, parsed_value, expected}.

    config.answer: {value, tolerance_abs?, tolerance_rel?, unit?, unit_credit?(0-1 缺/错单位保留), significant_digits?}
    """
    key = (config or {}).get("answer") or {}
    if "value" not in key:
        return {"correct": False, "earned": 0.0, "status": "unsatisfied",
                "reason": "题目缺少标准答案(value)", "parsed_value": None, "expected": None}
    key_value = float(key["value"])
    expected_unit = clean_unit(key.get("unit") or "")
    unit_credit = float(key.get("unit_credit", 0.3))
    sig_digits = key.get("significant_digits")

    exp_info = unit_info(expected_unit) if expected_unit else None
    # 期望单位不在表内 -> 退化为纯数值比对
    exp_machine_checkable = bool(expected_unit) and exp_info is not None

    value, unit, err = parse_numeric_answer(response_text)
    if value is None:
        return {"correct": False, "earned": 0.0, "status": "unsatisfied",
                "reason": err, "parsed_value": None, "expected": key_value}

    unit = clean_unit(unit)
    stu_info = unit_info(unit) if unit else None
    tol = dict(tol_abs=key.get("tolerance_abs"), tol_rel=key.get("tolerance_rel"))

    def _within(v):
        return compare_with_tolerance(v, key_value, **tol)

    # ---- 逐情形判定 ----
    # 情形 A: 无期望单位(或复合不可机检) -> 仅数值比对
    if not expected_unit or not exp_machine_checkable:
        ok = _within(value)
        note = "" if ok else "数值不在允许容差内"
        if ok and expected_unit:
            note = "数值比对通过(复合单位未做机器校验)"
        return {"correct": ok, "earned": 1.0 if ok else 0.0,
                "status": "satisfied" if ok else "unsatisfied",
                "reason": note, "parsed_value": value, "expected": key_value}

    # 情形 B: 期望单位可机检
    exp_family, exp_factor = exp_info
    stu_missing = not unit
    stu_unknown = (not stu_missing) and stu_info is None

    if stu_unknown:
        # 单位不可识别(可能串在别处)
        raw_ok = _within(value)
        reason = f"单位「{unit}」未识别"
        if raw_ok:
            return {"correct": False, "earned": round(unit_credit, 2),
                    "status": "partial", "reason": reason + "; 数值本身正确",
                    "parsed_value": value, "expected": key_value}
        return {"correct": False, "earned": 0.0, "status": "unsatisfied",
                "reason": reason, "parsed_value": value, "expected": key_value}

    if stu_missing:
        # 没写单位: 数值按同单位比; 数值对则给"缺单位"部分分
        raw_ok = _within(value)
        if raw_ok:
            return {"correct": False, "earned": round(unit_credit, 2),
                    "status": "partial", "reason": "缺少单位; 数值本身正确",
                    "parsed_value": value, "expected": key_value}
        return {"correct": False, "earned": 0.0, "status": "unsatisfied",
                "reason": "数值不在允许容差内(且缺少单位)", "parsed_value": value,
                "expected": key_value}

    # 写了单位且可识别
    stu_family, stu_factor = stu_info
    if stu_family != exp_family:
        return {"correct": False, "earned": 0.0, "status": "unsatisfied",
                "reason": f"单位量纲与要求不符(要求 {expected_unit})",
                "parsed_value": value, "expected": key_value}

    conv = value * (stu_factor / exp_factor)
    num_ok = _within(conv)
    if not num_ok:
        return {"correct": False, "earned": 0.0, "status": "unsatisfied",
                "reason": f"按单位换算后数值不在允许容差内(标准 {key_value} {expected_unit})",
                "parsed_value": value, "expected": key_value}

    # 有效数字校核
    sig_ok, sig_note = True, ""
    if sig_digits:
        stu_sig = sigfigs_of(response_text)
        if stu_sig is not None and stu_sig != int(sig_digits):
            sig_ok, sig_note = False, f"有效数字不符(你填 {stu_sig} 位, 要求 {int(sig_digits)} 位)"
    if not sig_ok:
        return {"correct": False, "earned": float(key.get("sig_credit", 0.7)),
                "status": "partial", "reason": "数值与单位正确; " + sig_note,
                "parsed_value": value, "expected": key_value}
    return {"correct": True, "earned": 1.0, "status": "satisfied",
            "reason": "数值、单位、有效数字均正确",
            "parsed_value": value, "expected": key_value}
