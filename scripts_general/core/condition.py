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
    """
    旧版条件解析器（已修复组合条件短路问题，现同时支持逾期和未逾期）。
    
    支持格式：
    1. 旧格式："未逾期" 或 "未逾期&{逾期天数}小于/等于/大于N"
    2. 新格式（逾期）：用 & 连接的复合条件，如 "逾期&总欠款不为空&利息为空"
    3. 新格式（未逾期）：用 & 连接的复合条件，如 "未逾期&总欠款不为空&利息不为空"
    
    修复说明：2026-08-27 修复了 if-elif 短路导致组合条件不全的问题。
    现在采用"先提取所有标志位，最后统一合并"的方式。
    同日修复正则未锚定结尾导致 "未逾期&利息不为空" 被误判为无条件匹配的问题（添加 $），
    以及 "未逾期" 包含 "逾期" 子串导致基础条件分支永远走 else 的问题。
    """
    
    _OVERDUE_CONDITION_PATTERN = re.compile(r'未逾期(?:&\{逾期天数\}(小于|等于|大于)(\d+))?$')

    # ===== 安全类型转换工具 =====
    @staticmethod
    def _safe_float(value, default=0.0) -> float:
        """安全转 float，任何异常返回默认值"""
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            import re
            cleaned = re.sub(r'[^\d.]', '', value)
            if cleaned == '' or cleaned == '.':
                return default
            try:
                return float(cleaned)
            except ValueError:
                return default
        return default

    @staticmethod
    def _safe_int(value, default=0) -> int:
        """安全转 int，任何异常返回默认值"""
        if value is None:
            return default
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            import re
            cleaned = re.sub(r'[^\d]', '', value)
            if cleaned == '':
                return default
            try:
                return int(cleaned)
            except ValueError:
                return default
        return default

    def evaluate(self, condition_str: str, case: Dict[str, Any]) -> bool:
        result = self.evaluate_with_metadata(condition_str, case)
        return result["matched"]

    def evaluate_with_metadata(self, condition_str: str, case: Dict[str, Any]) -> Dict[str, Any]:
        # ===== 边界1：空条件 =====
        if not condition_str or pd.isna(condition_str):
            return {"matched": True, "parsed_condition": "无条件", "overdue_value": 0}
        
        condition_str = str(condition_str).strip()
        
        # ===== 边界2：旧格式（"未逾期&{逾期天数}..."） =====
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
            return {"matched": matched, "parsed_condition": parsed_condition, "overdue_value": overdue_value}
        
        # ===== 边界3：新格式（组合条件）- 使用标志位模式 =====
        # ---- 基础条件判断（支持“未逾期”和“逾期”） ----
        overdue_val = self._parse_overdue_value(case)
        if "未逾期" in condition_str:
            base_matched = (overdue_val == 0)  # 未逾期：逾期天数 == 0
            base_label = "未逾期"
        elif "逾期" in condition_str:
            # 条件包含"逾期"（不含"未逾期"），默认匹配逾期场景
            base_matched = True
            base_label = "逾期"
        else:
            base_matched = True
            base_label = "无逾期"
        
        # ----- 提取各个字段的标志位（None 表示该条件未出现） -----
        flag_total = True
        if "总欠款不为空" in condition_str:
            val = self._safe_float(case.get("总欠款_数值", 0))
            flag_total = val > 0
        elif "总欠款为空" in condition_str:
            val = self._safe_float(case.get("总欠款_数值", 0))
            flag_total = val == 0
        
        flag_principal = True
        if "本金不为空" in condition_str:
            val = self._safe_float(case.get("本金_数值", 0))
            flag_principal = val > 0
        elif "本金为空" in condition_str:
            val = self._safe_float(case.get("本金_数值", 0))
            flag_principal = val == 0
        
        flag_interest = True
        if "利息不为空" in condition_str:
            val = self._safe_float(case.get("利息_数值", 0))
            flag_interest = val > 0
        elif "利息为空" in condition_str:
            val = self._safe_float(case.get("利息_数值", 0))
            flag_interest = val == 0
        
        flag_penalty = True
        if "罚息不为空" in condition_str:
            val = self._safe_float(case.get("罚息_数值", 0))
            flag_penalty = val > 0
        elif "罚息为空" in condition_str:
            val = self._safe_float(case.get("罚息_数值", 0))
            flag_penalty = val == 0
        
        flag_overdue_count = True
        if "逾期笔数不为空" in condition_str:
            val = self._safe_int(case.get("逾期笔数_数值", 0))
            flag_overdue_count = val > 0
        elif "逾期笔数为空" in condition_str:
            val = self._safe_int(case.get("逾期笔数_数值", 0))
            flag_overdue_count = val == 0
        
        # ----- 收集所有非 None 的标志位 -----
        flags = [
            f for f in [
                flag_total, flag_principal, flag_interest, 
                flag_penalty, flag_overdue_count
            ] if f is not None
        ]
        
        # ----- 合并结果 -----
        if not flags:
            # 只有基础条件
            matched = base_matched
            parsed_condition = base_label
        else:
            matched = base_matched and all(flags)
            # 构造可读的条件描述（用于追踪）
            condition_parts = [base_label]
            for flag, label in zip(
                [flag_total, flag_principal, flag_interest, flag_penalty, flag_overdue_count],
                ["总欠款", "本金", "利息", "罚息", "逾期笔数"]
            ):
                if flag is not None:
                    condition_parts.append(f"{label}{'' if flag else '为空?'}")
            parsed_condition = " & ".join(condition_parts)
        
        return {
            "matched": matched,
            "parsed_condition": parsed_condition,
            "overdue_value": overdue_val,
            "atomic_results": {
                base_label: base_matched,
                "总欠款": flag_total,
                "本金": flag_principal,
                "利息": flag_interest,
                "罚息": flag_penalty,
                "逾期笔数": flag_overdue_count,
            }
        }
    