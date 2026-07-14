"""
条件解析器模块：定义条件评估接口及实现

支持的条件格式：
- 旧格式：检查是否包含"逾期"关键字
- 新格式（未逾期）：
  - "未逾期" → 无条件匹配
  - "未逾期&{逾期天数}小于0" → 逾期天数 < 0，且需取绝对值
  - "未逾期&{逾期天数}等于0" → 逾期天数 == 0
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Dict

import pandas as pd


class ConditionEvaluator(ABC):
    @abstractmethod
    def evaluate(self, condition_str: str, case: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    def evaluate_with_metadata(self, condition_str: str, case: Dict[str, Any]) -> Dict[str, Any]:
        pass


class KeywordConditionEvaluator(ConditionEvaluator):
    def evaluate(self, condition_str: str, case: Dict[str, Any]) -> bool:
        if not condition_str or pd.isna(condition_str):
            return True
        return "逾期" in str(condition_str)

    def evaluate_with_metadata(self, condition_str: str, case: Dict[str, Any]) -> Dict[str, Any]:
        if not condition_str or pd.isna(condition_str):
            return {
                "matched": True,
                "requires_abs_overdue": False,
                "parsed_condition": "无条件",
                "overdue_value": 0,
            }
        condition_str = str(condition_str).strip()
        matched = "逾期" in condition_str
        return {
            "matched": matched,
            "requires_abs_overdue": False,
            "parsed_condition": f"旧格式（包含'逾期'）",
            "overdue_value": 0,
        }


class OverdueConditionEvaluator(ConditionEvaluator):
    # 类变量在程序加载类定义时只编译一次
    _OVERDUE_CONDITION_PATTERN = re.compile(
        r'未逾期(?:&\{逾期天数\}(小于|等于|大于)(\d+))?'
    )

    def evaluate(self, condition_str: str, case: Dict[str, Any]) -> bool:
        result = self.evaluate_with_metadata(condition_str, case)
        return result["matched"]

    def evaluate_with_metadata(self, condition_str: str, case: Dict[str, Any]) -> Dict[str, Any]:
        if not condition_str or pd.isna(condition_str):
            return {
                "matched": True,
                "requires_abs_overdue": False,
                "parsed_condition": "无条件",
                "overdue_value": 0,
            }

        condition_str = str(condition_str).strip()
        match = self._OVERDUE_CONDITION_PATTERN.match(condition_str)

        if match:
            comparison_op = match.group(1)
            threshold_str = match.group(2)

            overdue_value = case.get("逾期天数_数值", 0)
            if overdue_value == 0:
                overdue_str = case.get("逾期天数", "0")
                try:
                    overdue_value = int(overdue_str)
                except (ValueError, TypeError):
                    overdue_value = 0

            matched = False
            requires_abs_overdue = False
            parsed_condition = "未逾期"

            if comparison_op is None:
                matched = True
                parsed_condition = "未逾期（无条件）"
            else:
                try:
                    threshold = int(threshold_str)
                except ValueError:
                    threshold = 0

                if comparison_op == "小于":
                    matched = overdue_value < threshold
                    requires_abs_overdue = overdue_value < 0
                    parsed_condition = f"未逾期&逾期天数<{threshold}"
                elif comparison_op == "等于":
                    matched = overdue_value == threshold
                    parsed_condition = f"未逾期&逾期天数=={threshold}"
                elif comparison_op == "大于":
                    matched = overdue_value > threshold
                    parsed_condition = f"未逾期&逾期天数>{threshold}"

            return {
                "matched": matched,
                "requires_abs_overdue": requires_abs_overdue,
                "parsed_condition": parsed_condition,
                "overdue_value": overdue_value,
            }

        return {
            "matched": "逾期" in condition_str,
            "requires_abs_overdue": False,
            "parsed_condition": f"旧格式（包含'逾期'）",
            "overdue_value": 0,
        }
