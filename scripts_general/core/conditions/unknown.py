"""
未知 token 兜底条件。

分词后未被任何已注册原子条件匹配的 token 走这里。
默认返回 True + warning（与原"未识别当无条件"语义一致）。
"""

import logging
from typing import Any, Dict

from core.conditions.atomic import AtomicCondition

logger = logging.getLogger("DialogueBuilder")


class UnknownTokenCondition(AtomicCondition):
    def __init__(self, strict: bool = False):
        self._strict = strict

    def match(self, s: str) -> bool:
        return False

    def evaluate(self, s: str, case: Dict[str, Any]) -> bool:
        if self._strict:
            raise ValueError(f"未知条件 token: {s}")
        logger.warning(f"未知条件 token（按无条件处理）: {s}")
        return True

    def describe(self, s: str) -> str:
        return f"未知({s})"
