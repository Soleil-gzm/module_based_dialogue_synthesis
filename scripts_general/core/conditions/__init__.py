"""
条件解析子包。

提供原子条件注册表 + 分词复合解析。
新增条件类型只需写一个 AtomicCondition 子类并 register。
"""

from core.conditions.base import ConditionEvaluator
from core.conditions.atomic import AtomicCondition, safe_float, safe_int, parse_overdue_value
from core.conditions.parser import ConditionParser
from core.conditions.passthrough import PassthroughCondition
from core.conditions.overdue_flag import OverdueFlagCondition
from core.conditions.overdue_days import OverdueDaysCondition
from core.conditions.field_nullability import FieldNullabilityCondition
from core.conditions.follow_info import FollowInfoCondition
from core.conditions.unknown import UnknownTokenCondition

__all__ = [
    "ConditionEvaluator",
    "AtomicCondition",
    "ConditionParser",
    "PassthroughCondition",
    "OverdueFlagCondition",
    "OverdueDaysCondition",
    "FieldNullabilityCondition",
    "FollowInfoCondition",
    "UnknownTokenCondition",
    "safe_float",
    "safe_int",
    "parse_overdue_value",
]
