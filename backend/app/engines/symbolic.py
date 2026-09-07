"""公式符号化题判分引擎(新题型 M12).

对「字母表达式」做结构等价判定: 学生输入与标准式在变量定义域内是否同一代数式。
设计: 确定性 + 幂等 + 可解释(输出等价依据); 空答/无法解析不静默判零, 强制转人工复核。

两条互为兜底的判定路径(结果如实标注方法名):
  1) sympy(若已安装): 解析后对差做符号化简/展开 -> diff 化简为 0 即等价(结构性判定);
  2) 数值抽样等价检验(默认, 离线无 sympy 时的确定性等价物):
     在变量声明域内用固定种子 Random(2026) 采 N 个点, 受限 eval 求两式数值,
     相对容差 1e-6(量级兜底 1.0)判点值一致; 一点不一致即证伪(数学反例);
     全部一致才判等价。变量域声明避零(如 m in [1,12]) 防除零采样。
"""
from __future__ import annotations

import ast
import math
import random
import re

from app.constants import LVL_FORCED, LVL_NONE, V_SATISFIED, V_UNSATISFIED
from app.engines.base import EngineOutcome, EvidenceHit

_SYMPY = None
try:  # 可选依赖: 装了走符号等价(更强); 未装退化为数值抽样, 行为仍确定
    import sympy as _SYMPY  # type: ignore
except Exception:  # pragma: no cover - 离线环境无 sympy 属正常
    _SYMPY = None

# eval 白名单: 仅提供纯数值函数/常量与声明的变量, 封禁 __builtins__
_MATH_NS = {k: v for k, v in vars(math).items() if not k.startswith("__")}

_SUP2 = str.maketrans({"²": "**2", "³": "**3", "⁴": "**4", "⁵": "**5",
                       "⁶": "**6", "⁷": "**7", "⁸": "**8", "⁹": "**9"})


def sanitize_formula_expr(text: str) -> str:
    """把作答/标准式规范成可解析表达式:
    去等号取右侧、×/·/÷ -> *、/、^ -> **、常见上标、中英文括号/空白。
    """
    s = str(text or "").strip().strip("。")
    # 若写成 "a=F/m" 这类含等号的式子, 只取右侧作为待判定的表达式
    s = s.rsplit("=", 1)[-1].strip()
    s = re.sub(r"[ \t　]+", "", s)
    s = s.replace("×", "*").replace("·", "*").replace("÷", "/")
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("π", "pi").replace("√", "sqrt")
    s = s.translate(_SUP2).replace("^", "**")
    return s.strip()


def _sympy_equivalent(expected: str, given: str) -> bool | None:
    """sympy 结构等价: 差化简为 0 判等价. 解析失败/无 sympy -> None(交给采样)."""
    if _SYMPY is None:
        return None
    try:
        a = _SYMPY.parse_expr(expected)
        b = _SYMPY.parse_expr(given)
        diff = _SYMPY.simplify(a - b)
        return diff == 0 or diff == _SYMPY.S.Zero
    except Exception:  # noqa: BLE001 - 语法不支持等情形退化为采样
        return None


def _find_free_vars(expr: str) -> set[str]:
    """粗略抽取纯标识符(小写字母序列, 排除 pi/e 等常量)供变量名候补."""
    consts = {"pi", "e", "exp", "log", "sqrt", "sin", "cos", "tan",
              "asin", "acos", "atan", "abs", "floor", "ceil"}
    found: set[str] = set()
    for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr):
        if tok not in consts and tok not in {"max", "min"}:
            found.add(tok)
    return found


def _eval_safe(code: str, values: dict) -> float:
    """受限求值(白名单 AST, 不用内置 eval): 仅允许数值常量/四则/幂、
    已声明变量与 math 白名单函数; 任何属性访问/下标/调用未知符号/下划线
    名一律拒绝 -> 抛异常转人工。学生输入不可触达解释器内部对象。

    语义与旧实现对齐: 命名空间 = math 白名单 + 该点变量值(不含 __builtins__)。
    """
    ns = dict(_MATH_NS)
    ns.update(values)
    return _ast_eval_only_math(code, ns)


def _ast_eval_only_math(code: str, ns: dict) -> float:
    """对公式表达式做安全 AST 求值。只放行可验证为纯数值计算的节点。"""
    _MAX_POW_EXP = 512  # 封顶指数, 防超大整数指数造成内存/CPU 消耗

    def _err() -> ValueError:
        return ValueError("公式含不支持的结构(仅允许数字/四则运算/数学函数/已声明变量)")

    try:
        tree = ast.parse(code, mode="eval")
    except SyntaxError:
        raise _err() from None

    def _walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _walk(node.body)
        if isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, bool) or isinstance(v, (int, float)):
                return float(v)
            raise _err()
        if isinstance(node, ast.Name):
            name = node.id
            if name.startswith("__") or name not in ns:
                raise _err()
            val = ns[name]
            if callable(val):
                # 名字本身不作为数值出现; 只在 Call 处按函数调用
                raise _err()
            return float(val)
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, (ast.UAdd, ast.USub)):
                v = _walk(node.operand)
                return v if isinstance(node.op, ast.UAdd) else -v
            raise _err()
        if isinstance(node, ast.BinOp):
            left, right = _walk(node.left), _walk(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise ZeroDivisionError("除零")
                return left / right
            if isinstance(node.op, ast.FloorDiv):
                if right == 0:
                    raise ZeroDivisionError("除零")
                return math.floor(left / right)
            if isinstance(node.op, ast.Mod):
                if right == 0:
                    raise ZeroDivisionError("除零")
                return left % right
            if isinstance(node.op, ast.Pow):
                if abs(right) > _MAX_POW_EXP:
                    raise _err()
                return left ** right
            raise _err()
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.keywords:
                raise _err()
            fn_name = node.func.id
            if fn_name.startswith("__") or fn_name not in ns or not callable(ns[fn_name]):
                raise _err()
            fn = ns[fn_name]
            args = [_walk(a) for a in node.args]
            try:
                return float(fn(*args))
            except (TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
                raise _err() from exc
        raise _err()

    return _walk(tree)


def _sampling_equivalent(expected: str, given: str, variables: list[dict],
                         n: int = 12, seed: int = 2026,
                         rel_tol: float = 1e-6) -> tuple[bool, int, int] | None:
    """数值抽样等价检验. 返回 (等价?, 有效点数, 不一致点数); 无法采样 -> None.

    判定: 任一有效点两式差超过相对容差 -> 数学反例, 判不等价(确定性)。
    全部有效点一致且有效点足够 -> 判等价。
    """
    ranges: dict[str, tuple[float, float]] = {}
    for v in variables or []:
        name = str(v.get("name", "")).strip()
        if not name:
            continue
        try:
            lo, hi = float(v.get("min", -10.0)), float(v.get("max", 10.0))
        except (TypeError, ValueError):  # pragma: no cover
            continue
        if hi < lo:
            lo, hi = hi, lo
        if lo == hi:
            hi = lo + 1.0
        ranges[name] = (lo, hi)
    # 若未显式声明变量, 从表达式里抽取; 域名默认 [-10, 10]
    for nm in sorted(_find_free_vars(expected) | _find_free_vars(given)):
        if nm not in ranges:
            ranges[nm] = (-10.0, 10.0)
    if not ranges:
        # 纯常量表达式: 直接比较一次(如 6.28 vs 2*pi)
        try:
            a = _eval_safe(expected, {})
            b = _eval_safe(given, {})
        except Exception:  # noqa: BLE001
            return None
        return (math.isfinite(a) and math.isfinite(b)
                and abs(a - b) <= rel_tol * max(abs(a), abs(b), 1.0)), 1, 0

    names = sorted(ranges)
    rng = random.Random(seed)
    sample_count = max(n, 4 * len(names) + 4)
    valid = mismatch = 0
    for _ in range(sample_count):
        values = {nm: rng.uniform(lo, hi) for nm, (lo, hi) in ranges.items()}
        try:
            a = _eval_safe(expected, values)
            b = _eval_safe(given, values)
        except Exception:  # noqa: BLE001 - 语法不支持/未知符号 -> 该点无效
            continue
        if not (math.isfinite(a) and math.isfinite(b)):
            continue  # 采样撞到奇点, 跳过(不当作反例)
        valid += 1
        if abs(a - b) > rel_tol * max(abs(a), abs(b), 1.0):
            mismatch += 1
    if valid < max(2, sample_count // 3):
        return None  # 有效样本太少, 无从判定 -> 转人工
    return mismatch == 0, valid, mismatch


def grade_formula(cfg: dict, response: str, max_score: float,
                  policy: dict | None = None, method: str = "auto") -> EngineOutcome:
    """公式符号化题统一判分入口(确定性; 异常/空答转人工复核)."""
    f = dict((cfg or {}).get("formula") or {})
    expected_raw = f.get("expected") or (cfg or {}).get("expected") or ""
    variables = f.get("variables")
    if variables is None:
        variables = (cfg or {}).get("variables") or []

    given = sanitize_formula_expr(response)
    expected = sanitize_formula_expr(expected_raw)

    if not given:
        return _formula_outcome(0.0, max_score, LVL_FORCED, V_UNSATISFIED,
                                "空答或未识别到公式作答, 转人工复核。",
                                method="none", expected=expected, given=given)
    if not expected:
        return _formula_outcome(0.0, max_score, LVL_FORCED, V_UNSATISFIED,
                                "题目未配置标准公式(expected), 无法自动判分。",
                                method="none", expected=expected, given=given)

    # 路径选择: auto = sympy 优先, 不可用/解析失败 -> 数值抽样
    use_sympy = method == "sympy" or (method == "auto" and _SYMPY is not None)
    if use_sympy:
        eq = _sympy_equivalent(expected, given)
        if eq is not None:
            method_name = "sympy"
        else:
            eq = None
            method_name = None
    else:
        eq, method_name = None, None

    if eq is None:
        # 符号不可用/解析失败 -> 数值抽样等价检验
        if method == "sympy":
            return _formula_outcome(0.0, max_score, LVL_FORCED, V_UNSATISFIED,
                                    "要求 sympy 但未安装/解析失败, 无法符号判定, 转人工复核。",
                                    method="none", expected=expected, given=given)
        res = _sampling_equivalent(expected, given, variables)
        if res is None:
            return _formula_outcome(0.0, max_score, LVL_FORCED, V_UNSATISFIED,
                                    "作答无法在变量域内数值求值(含未声明符号/语法错误), 转人工复核。",
                                    method="sampling_unresolved", expected=expected,
                                    given=given)
        eq, valid, mismatch = res
        method_name = "numeric_sampling"
        if eq:
            reason = (f"数值抽样等价检验通过: 在 {valid} 个采样点({','.join(v['name'] for v in variables) or '常数'})"
                      f" 上两式一致。")
        else:
            reason = (f"数值抽样等价检验不通过: 至少 1 个采样点上两式数值不一致"
                      f"(共 {valid} 有效点, {mismatch} 点不符)。")
        conf = 0.98 if eq else 0.97
    else:
        method_name = "sympy"
        reason = f"符号化简后两式之差为 0, 判定结构等价(标准式 {expected})。" if eq \
            else f"符号化简后两式之差不为 0, 判定不等价(标准式 {expected})。"
        conf = 1.0

    if eq:
        earned = float(max_score)
        status = V_SATISFIED
    else:
        # 确定性判错: 与客观题一致自动放行(0 分), 而非静默吞掉
        earned = 0.0
        status = V_UNSATISFIED
    # 额外展示判定详情
    detail = f"method={method_name}; 标准式 {expected}; 你的式子 {given}; {reason}"
    return _formula_outcome(earned, max_score, LVL_NONE, status, reason,
                            method=method_name, expected=expected, given=given,
                            detail=detail, confidence=conf)


def _formula_outcome(earned: float, max_score: float, review_level: str,
                     status: str, reason: str, *, method: str, expected: str,
                     given: str, detail: str = "", confidence: float = 1.0) -> EngineOutcome:
    hit = EvidenceHit(label=status, kind="symbolic", snippet=(reason or detail)[:400])
    extra = {"method": method, "expected": expected, "given": given}
    if detail:
        extra["detail"] = detail
    return EngineOutcome(
        total=round(max(0.0, min(earned, max_score)), 2), max_score=max_score,
        point_results=[], penalties=[], hits=[hit], comment="",
        reasoning=reason or detail, confidence=confidence,
        review_level=review_level, extra=extra,
    )
