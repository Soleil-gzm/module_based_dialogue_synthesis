"""
字段空/非空条件（token 级，通用模板）。

匹配 `X不为空` / `X为空`，X ∈ {总欠款, 本金, 利息, 罚息, 逾期笔数}。
新增字段只需在 FIELD_MAP 加一行，消除原 if-elif 重复。
"""

import re
from typing import Any, Dict

from core.conditions.atomic import AtomicCondition, safe_float, safe_int

_PATTERN = re.compile(r"^(总欠款|本金|利息|罚息|逾期笔数)(不为空|为空)$")

# 字段名 → case 中的数值键 + 转换函数
_FIELD_MAP = {
    "总欠款": ("总欠款_数值", safe_float),
    "本金": ("本金_数值", safe_float),
    "利息": ("利息_数值", safe_float),
    "罚息": ("罚息_数值", safe_float),
    "逾期笔数": ("逾期笔数_数值", safe_int),
}


class FieldNullabilityCondition(AtomicCondition):
    def match(self, s: str) -> bool:
        return bool(_PATTERN.match(s))

    def evaluate(self, s: str, case: Dict[str, Any]) -> bool:
        m = _PATTERN.match(s)
        if not m:
            return False
        field, op = m.group(1), m.group(2)
        case_key, convert = _FIELD_MAP[field]
        val = convert(case.get(case_key, 0))
        return (val > 0) if op == "不为空" else (val == 0)

    def describe(self, s: str) -> str:
        return s
