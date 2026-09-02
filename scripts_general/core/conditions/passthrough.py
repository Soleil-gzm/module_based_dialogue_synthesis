"""空条件：无条件匹配，恒返回 True。"""

from typing import Any, Dict

from core.conditions.atomic import AtomicCondition


class PassthroughCondition(AtomicCondition):
    """匹配空字符串 / NaN，求值恒 True"""

    def match(self, s: str) -> bool:
        return False

    def evaluate(self, s: str, case: Dict[str, Any]) -> bool:
        return True

    def describe(self, s: str) -> str:
        return "无条件"
