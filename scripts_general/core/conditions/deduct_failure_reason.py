"""
代扣结果条件（token 级）。

匹配写法：`代扣结果为XXX`
其中 XXX ∈ {无代扣协议, 银行卡异常, 无}

从 case 的"代扣结果"字段取值做精确匹配。
支持 `|` 作为同类型 OR：`代扣结果为无代扣协议|代扣结果为银行卡异常`
  → 代扣结果为"无代扣协议"或"银行卡异常"时命中。
"""

import re
from typing import Any, Dict, List

from core.conditions.atomic import AtomicCondition

# 已知的代扣结果值（用于校验，防止误匹配其他条件）
_KNOWN_RESULTS = {"无代扣协议", "银行卡异常", "无"}

# 前缀形式：代扣结果为XXX
_PREFIX_PATTERN = re.compile(r"^代扣结果为(.+)$")


class DeductFailureReasonCondition(AtomicCondition):
    def _parse_parts(self, s: str) -> List[str]:
        """
        将 token 解析为值列表。
        - 支持 `|` 分隔的多值 OR
        - 每个片段格式为 `代扣结果为XXX`
        - 只要有一个片段无法识别或值不在白名单，返回空列表（表示 match 失败）
        """
        values = []
        for part in s.split("|"):
            part = part.strip()
            if not part:
                continue
            m = _PREFIX_PATTERN.match(part)
            if not m:
                return []  # 前缀不匹配，不归我管
            value = m.group(1).strip()
            if value not in _KNOWN_RESULTS:
                return []  # 值不在白名单，不归我管
            values.append(value)
        return values

    def match(self, s: str) -> bool:
        return len(self._parse_parts(s)) > 0

    def evaluate(self, s: str, case: Dict[str, Any]) -> bool:
        result = case.get("代扣结果", "")
        if not result:
            return False
        values = self._parse_parts(s)
        return result in values

    def describe(self, s: str) -> str:
        values = self._parse_parts(s)
        if len(values) == 1:
            return f"代扣结果={values[0]}"
        return f"代扣结果={'|'.join(values)}"