"""
逾期/未逾期标志条件（token 级）。

逾期和未逾期是写表人员用来标记业务场景的标签，不参与条件判断，恒返回 True。
"""

from typing import Any, Dict

from core.conditions.atomic import AtomicCondition


class OverdueFlagCondition(AtomicCondition):
    def match(self, s: str) -> bool:
        return s in ("未逾期", "逾期")

    def evaluate(self, s: str, case: Dict[str, Any]) -> bool:
        return True

    def describe(self, s: str) -> str:
        return f"{s}(标签)"
