"""
旧格式整体匹配条件。

匹配 `未逾期` 或 `未逾期&{逾期天数}(小于|等于|大于)N` 整个字符串。
这是遗留兼容路径，作为"整体匹配"条件注册到 parser 优先层。

行为（黄金样本锁定）：
- 裸 `未逾期` → 恒 True（不校验逾期天数，保留原行为）
- `未逾期&{逾期天数}小于N` → overdue < N
- `未逾期&{逾期天数}等于N` → overdue == N
- `未逾期&{逾期天数}大于N` → overdue > N
"""

import re
from typing import Any, Dict

from core.conditions.atomic import AtomicCondition, parse_overdue_value

_PATTERN = re.compile(r"未逾期(?:&\{逾期天数\}(小于|等于|大于)(\d+))?$")


class OverdueLegacyCondition(AtomicCondition):
    """整体匹配旧格式 `未逾期[&{逾期天数}X]`"""

    def match(self, s: str) -> bool:
        return bool(_PATTERN.match(s))

    def evaluate(self, s: str, case: Dict[str, Any]) -> bool:
        m = _PATTERN.match(s)
        if not m:
            return False
        op, threshold_str = m.group(1), m.group(2)
        if op is None:
            return True
        try:
            threshold = int(threshold_str)
        except ValueError:
            threshold = 0
        overdue = parse_overdue_value(case)
        if op == "小于":
            return overdue < threshold
        if op == "等于":
            return overdue == threshold
        if op == "大于":
            return overdue > threshold
        return False

    def describe(self, s: str) -> str:
        m = _PATTERN.match(s)
        if not m:
            return s
        op, threshold_str = m.group(1), m.group(2)
        if op is None:
            return "未逾期（无条件）"
        return f"未逾期&逾期天数{op}{threshold_str}"
