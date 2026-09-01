"""
逾期标志条件（token 级）。

在分词路径中匹配独立的 `未逾期` 或 `逾期` token。
与 OverdueLegacyCondition 的区别：本类出现在复合条件分词后，会校验逾期天数。

行为（与原新格式逻辑一致）：
- token == "未逾期" → overdue == 0
- token == "逾期"   → 恒 True（遗留兼容）
"""

from typing import Any, Dict

from core.conditions.atomic import AtomicCondition, parse_overdue_value


class OverdueFlagCondition(AtomicCondition):
    def match(self, s: str) -> bool:
        return s in ("未逾期", "逾期")

    def evaluate(self, s: str, case: Dict[str, Any]) -> bool:
        if s == "未逾期":
            return parse_overdue_value(case) == 0
        return True

    def describe(self, s: str) -> str:
        if s == "未逾期":
            return "未逾期"
        return "逾期"
