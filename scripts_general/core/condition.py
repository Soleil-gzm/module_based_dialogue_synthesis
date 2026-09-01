"""
条件解析器模块（门面）。

实际逻辑由 core.conditions 子包实现。本模块保留旧 import 路径以兼容调用方：
    from core.condition import ConditionEvaluator, ConditionParser
"""

from core.conditions import ConditionEvaluator, ConditionParser

__all__ = ["ConditionEvaluator", "ConditionParser"]
