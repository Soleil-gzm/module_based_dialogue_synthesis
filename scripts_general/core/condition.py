"""
条件解析器模块：定义条件评估接口及实现。

实际解析逻辑由 core.conditions 子包的原子条件注册表 + 分词复合解析完成。
本模块保留 ConditionEvaluator ABC 和旧实现类签名，以兼容现有调用方。

支持的条件格式：
- 旧格式："未逾期" 或 "未逾期&{逾期天数}(小于|等于|大于)N"
- 新格式：用 & 连接的复合条件，如 "未逾期&总欠款不为空&利息为空"
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict

import pandas as pd

logger = logging.getLogger("DialogueBuilder")


class ConditionEvaluator(ABC):
    @abstractmethod
    def evaluate(self, condition_str: str, case: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    def evaluate_with_metadata(self, condition_str: str, case: Dict[str, Any]) -> Dict[str, Any]:
        pass

    def _parse_overdue_value(self, case: Dict[str, Any]) -> int:
        """从case中解析逾期天数数值，用于条件判断"""
        overdue_str = case.get("逾期天数", "0")
        try:
            return int(overdue_str)
        except (ValueError, TypeError):
            return 0


class KeywordConditionEvaluator(ConditionEvaluator):
    def evaluate(self, condition_str: str, case: Dict[str, Any]) -> bool:
        if not condition_str or pd.isna(condition_str):
            return True
        return "逾期" in str(condition_str)

    def evaluate_with_metadata(self, condition_str: str, case: Dict[str, Any]) -> Dict[str, Any]:
        if not condition_str or pd.isna(condition_str):
            return {
                "matched": True,
                "parsed_condition": "无条件",
                "overdue_value": 0,
            }
        condition_str = str(condition_str).strip()
        matched = "逾期" in condition_str
        return {
            "matched": matched,
            "parsed_condition": f"旧格式（包含'逾期'）",
            "overdue_value": 0,
        }


class OverdueConditionEvaluator(ConditionEvaluator):
    """
    条件解析器（委托 core.conditions.ConditionParser）。

    实际解析逻辑由原子条件注册表 + 分词复合解析完成，见 core/conditions/。
    本类仅保留旧 API 签名以兼容现有调用方。

    行为（由黄金样本锁定）：
    1. 裸 "未逾期" → 恒 True（不校验逾期天数，保留原行为）
    2. "未逾期&{逾期天数}小于/等于/大于N" → 仅看天数比较
    3. "未逾期&字段条件" → 校验 overdue==0 AND 各字段条件
    4. "逾期" → 恒 True
    """

    def __init__(self):
        from core.conditions import ConditionParser
        self._parser = ConditionParser()

    def evaluate(self, condition_str: str, case: Dict[str, Any]) -> bool:
        return self._parser.evaluate(condition_str, case)

    def evaluate_with_metadata(self, condition_str: str, case: Dict[str, Any]) -> Dict[str, Any]:
        return self._parser.evaluate_with_metadata(condition_str, case)
