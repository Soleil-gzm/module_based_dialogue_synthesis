"""
代扣失败原因条件（token 级）。

匹配两种写法：
1. 裸值形式：`无代扣协议`、`银行卡异常`、`无`
2. 明确前缀形式：`代扣失败原因为无代扣协议`

从 case 的"代扣失败原因"字段取值做精确匹配。
支持 `|` 作为同类型 OR：`无代扣协议|银行卡异常`
  → 代扣失败原因为"无代扣协议"或"银行卡异常"时命中。
"""

import re
from typing import Any, Dict, List

from core.conditions.atomic import AtomicCondition

# 已知的代扣失败原因值（裸 token 形式）
_KNOWN_REASONS = {"无代扣协议", "银行卡异常", "无"}

# 明确前缀形式：代扣失败原因为XXX
_PREFIX_PATTERN = re.compile(r"^代扣失败原因为(.+)$")


class DeductFailureReasonCondition(AtomicCondition):
    def _parse_parts(self, s: str) -> List[str]:
        """
        将 token 解析为值列表。
        - 支持 `|` 分隔的多值 OR
        - 每个片段可以是 `代扣失败原因为XXX` 或裸值 `XXX`
        - 只要有一个片段无法识别，返回空列表（表示 match 失败）
        """
        values = []
        for part in s.split("|"):
            part = part.strip()
            if not part:
                continue
            m = _PREFIX_PATTERN.match(part)
            if m:
                values.append(m.group(1))
            elif part in _KNOWN_REASONS:
                values.append(part)
            else:
                return []  # 包含未知片段，不归我管
        return values

    def match(self, s: str) -> bool:
        return len(self._parse_parts(s)) > 0

    def evaluate(self, s: str, case: Dict[str, Any]) -> bool:
        reason = case.get("代扣失败原因", "")
        if not reason:
            return False
        values = self._parse_parts(s)
        return reason in values

    def describe(self, s: str) -> str:
        values = self._parse_parts(s)
        if len(values) == 1:
            return f"代扣失败原因={values[0]}"
        return f"代扣失败原因={'|'.join(values)}"