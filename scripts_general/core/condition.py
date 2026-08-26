"""
条件解析器模块：定义条件评估接口及实现

支持的条件格式：
- 旧格式：检查是否包含"逾期"关键字
- 新格式（未逾期）：
  - "未逾期" → 无条件匹配
  - "未逾期&{逾期天数}小于0" → 逾期天数 < 0
  - "未逾期&{逾期天数}等于0" → 逾期天数 == 0
"""

import re
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
                "parsed_condition": "无条件",
                "overdue_value": 0,
            }

        # ===== 清洗不可见字符（防全角空格等） =====
        condition_str = str(condition_str).strip().replace('\u00A0', ' ').replace('\u3000', ' ')
        # ===== 清洗结束 =====

        # ===== 新增：临时处理新甲方的复合条件（2026-08-26任务） =====
        # 基础判断：是否包含"逾期"关键词
        base_has_overdue = "逾期" in condition_str
        
        # 针对新字段的具体判断（为空 = 数值 == 0）
        if "总欠款不为空" in condition_str:
            val = case.get("总欠款_数值", 0)
            matched = base_has_overdue and (val > 0)
            # logger.debug(f"条件判断: {condition_str} -> 总欠款_数值={val}, 结果={matched}")
            return {"matched": matched, "parsed_condition": "逾期&总欠款>0", "overdue_value": self._parse_overdue_value(case)}
        elif "总欠款为空" in condition_str:
            val = case.get("总欠款_数值", 0)
            matched = base_has_overdue and (val == 0)
            # logger.debug(f"条件判断: {condition_str} -> 总欠款_数值={val}, 结果={matched}")
            return {"matched": matched, "parsed_condition": "逾期&总欠款==0", "overdue_value": self._parse_overdue_value(case)}
        elif "本金不为空" in condition_str:
            val = case.get("本金_数值", 0)
            matched = base_has_overdue and (val > 0)
            # logger.debug(f"条件判断: {condition_str} -> 本金_数值={val}, 结果={matched}")
            return {"matched": matched, "parsed_condition": "逾期&本金>0", "overdue_value": self._parse_overdue_value(case)}
        elif "本金为空" in condition_str:
            val = case.get("本金_数值", 0)
            matched = base_has_overdue and (val == 0)
            # logger.debug(f"条件判断: {condition_str} -> 本金_数值={val}, 结果={matched}")
            return {"matched": matched, "parsed_condition": "逾期&本金==0", "overdue_value": self._parse_overdue_value(case)}
        elif "逾期笔数不为空" in condition_str:
            val = case.get("逾期笔数_数值", 0)
            matched = base_has_overdue and (val > 0)
            # logger.debug(f"条件判断: {condition_str} -> 逾期笔数_数值={val}, 结果={matched}")
            return {"matched": matched, "parsed_condition": "逾期&逾期笔数>0", "overdue_value": self._parse_overdue_value(case)}
        elif "逾期笔数为空" in condition_str:
            val = case.get("逾期笔数_数值", 0)
            matched = base_has_overdue and (val == 0)
            # logger.debug(f"条件判断: {condition_str} -> 逾期笔数_数值={val}, 结果={matched}")
            return {"matched": matched, "parsed_condition": "逾期&逾期笔数==0", "overdue_value": self._parse_overdue_value(case)}
        elif "利息不为空" in condition_str:
            val = case.get("利息_数值", 0)
            matched = base_has_overdue and (val > 0)
            # logger.debug(f"条件判断: {condition_str} -> 逾期笔数_数值={val}, 结果={matched}")
            return {"matched": matched, "parsed_condition": "逾期&利息>0", "overdue_value": self._parse_overdue_value(case)}
        elif "利息为空" in condition_str:
            val = case.get("利息_数值", 0)
            matched = base_has_overdue and (val == 0)
            # logger.debug(f"条件判断: {condition_str} -> 逾期笔数_数值={val}, 结果={matched}")
            return {"matched": matched, "parsed_condition": "逾期&利息==0", "overdue_value": self._parse_overdue_value(case)}
        elif "罚息不为空" in condition_str:
            val = case.get("罚息_数值", 0)
            matched = base_has_overdue and (val > 0)
            # logger.debug(f"条件判断: {condition_str} -> 逾期笔数_数值={val}, 结果={matched}")
            return {"matched": matched, "parsed_condition": "逾期&罚息>0", "overdue_value": self._parse_overdue_value(case)}
        elif "罚息为空" in condition_str:
            val = case.get("罚息_数值", 0)
            matched = base_has_overdue and (val == 0)
            # logger.debug(f"条件判断: {condition_str} -> 逾期笔数_数值={val}, 结果={matched}")
            return {"matched": matched, "parsed_condition": "逾期&罚息==0", "overdue_value": self._parse_overdue_value(case)}
        # ===== 新增结束 =====

        # 旧格式：处理 "未逾期&{逾期天数}小于/等于/大于N" 或 "未逾期"
        match = self._OVERDUE_CONDITION_PATTERN.match(condition_str)

        if match:
            comparison_op = match.group(1)
            threshold_str = match.group(2)
            overdue_value = self._parse_overdue_value(case)

            matched = False
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
                    parsed_condition = f"未逾期&逾期天数<{threshold}"
                elif comparison_op == "等于":
                    matched = overdue_value == threshold
                    parsed_condition = f"未逾期&逾期天数=={threshold}"
                elif comparison_op == "大于":
                    matched = overdue_value > threshold
                    parsed_condition = f"未逾期&逾期天数>{threshold}"

            # logger.debug(f"条件判断(旧格式): {condition_str} -> 逾期天数={overdue_value}, 结果={matched}")
            return {
                "matched": matched,
                "parsed_condition": parsed_condition,
                "overdue_value": overdue_value,
            }

        # 如果既没命中新条件，也没命中旧正则，最后回退到仅判断是否包含"逾期"
        fallback_matched = "逾期" in condition_str
        # logger.warning(f"条件未命中任何分支，使用回退逻辑: {condition_str} -> {fallback_matched}")
        return {
            "matched": fallback_matched,
            "parsed_condition": f"回退（包含'逾期'）",
            "overdue_value": 0,
        }