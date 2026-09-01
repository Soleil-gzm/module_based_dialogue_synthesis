"""
原子条件基类与共享工具函数。
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Dict


class AtomicCondition(ABC):
    """
    单个原子条件的抽象基类。

    一个原子条件负责：
    - match(s): 判断给定字符串（整体或单个 token）是否归我管
    - evaluate(s, case): 对该字符串求值
    - describe(s): 返回可读描述，供 trace 使用
    """

    @abstractmethod
    def match(self, s: str) -> bool:
        ...

    @abstractmethod
    def evaluate(self, s: str, case: Dict[str, Any]) -> bool:
        ...

    @abstractmethod
    def describe(self, s: str) -> str:
        ...


def safe_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^\d.]", "", value)
        if cleaned == "" or cleaned == ".":
            return default
        try:
            return float(cleaned)
        except ValueError:
            return default
    return default


def safe_int(value, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^\d]", "", value)
        if cleaned == "":
            return default
        try:
            return int(cleaned)
        except ValueError:
            return default
    return default


def parse_overdue_value(case: Dict[str, Any]) -> int:
    """从 case 中解析逾期天数，异常时返回 0"""
    try:
        return int(case.get("逾期天数", 0))
    except (ValueError, TypeError):
        return 0
