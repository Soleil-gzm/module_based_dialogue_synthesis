"""
跟催信息条件（token 级）。

匹配 `跟催信息为XXX`，如 `跟催信息为未接通`、`跟催信息为承诺还款`。
支持 `|` 作为同类型 OR：`跟催信息为协商诉求|跟催信息为投诉风险`
  → 跟催信息为"协商诉求"或"投诉风险"时命中。
"""

import re
from typing import Any, Dict, List

from core.conditions.atomic import AtomicCondition

_PATTERN = re.compile(r"^跟催信息为(.+)$")


class FollowInfoCondition(AtomicCondition):
    def match(self, s: str) -> bool:
        parts = s.split("|")
        return len(parts) > 0 and all(_PATTERN.match(p.strip()) for p in parts)

    def evaluate(self, s: str, case: Dict[str, Any]) -> bool:
        follow_info = case.get("跟催信息", "")
        if not follow_info:
            return False
        parts = [p.strip() for p in s.split("|")]
        for part in parts:
            m = _PATTERN.match(part)
            if m and m.group(1) == follow_info:
                return True
        return False

    def describe(self, s: str) -> str:
        parts = [p.strip() for p in s.split("|")]
        values = []
        for part in parts:
            m = _PATTERN.match(part)
            if m:
                values.append(m.group(1))
        if len(values) == 1:
            return f"跟催信息={values[0]}"
        return f"跟催信息={'|'.join(values)}"
