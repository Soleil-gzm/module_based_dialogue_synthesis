"""
逾期天数比较条件（token 级）。

匹配 `{逾期天数}(小于|等于|大于)N`，如 `{逾期天数}小于0`、`{逾期天数}等于5`。
从 case 的"逾期天数"字段取值做比较。
"""

import re
from typing import Any, Dict

from core.conditions.atomic import AtomicCondition, parse_overdue_value

_PATTERN = re.compile(r"^\{逾期天数\}(小于|等于|大于)(\d+)$")


class OverdueDaysCondition(AtomicCondition):
    def match(self, s: str) -> bool:
        return bool(_PATTERN.match(s))

    def evaluate(self, s: str, case: Dict[str, Any]) -> bool:
        m = _PATTERN.match(s)
        if not m:
            return False
        op, threshold_str = m.group(1), m.group(2)
        try:
            threshold = int(threshold_str)
        except ValueError:
            return False
        overdue = parse_overdue_value(case)
        if op == "小于":
            return overdue < threshold
        if op == "等于":
            return overdue == threshold
        if op == "大于":
            return overdue > threshold
        return False

    def describe(self, s: str) -> str:
        return s
