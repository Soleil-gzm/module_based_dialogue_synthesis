"""
条件解析器：原子条件注册表 + 分词复合解析。

解析流程（优先级从高到低）：
1. 空条件 / NaN → 恒 True
2. 整体匹配层（whole_str）：旧格式 `未逾期[&{逾期天数}X]` 整体命中则单独求值
3. 分词层：按 `&` 拆分，逐 token 查注册表，全部 AND 组合

新增条件类型只需写一个 AtomicCondition 子类并 register，主体逻辑不动。
"""

from functools import partial
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from core.conditions.base import ConditionEvaluator
from core.conditions.atomic import AtomicCondition, parse_overdue_value
from core.conditions.overdue_legacy import OverdueLegacyCondition
from core.conditions.overdue_flag import OverdueFlagCondition
from core.conditions.field_nullability import FieldNullabilityCondition
from core.conditions.unknown import UnknownTokenCondition


class ConditionParser(ConditionEvaluator):
    def __init__(self, strict: bool = False):
        self._whole_str: List[AtomicCondition] = []
        self._token: List[AtomicCondition] = []
        self._unknown = UnknownTokenCondition(strict=strict)
        self._register_defaults()

    def _register_defaults(self):
        self.register_whole(OverdueLegacyCondition())
        self.register_token(OverdueFlagCondition())
        self.register_token(FieldNullabilityCondition())

    def register_whole(self, cond: AtomicCondition) -> None:
        self._whole_str.append(cond)

    def register_token(self, cond: AtomicCondition) -> None:
        self._token.append(cond)

    def parse(self, condition_str) -> Tuple[Callable[[Dict[str, Any]], bool], List[AtomicCondition], List[str], List[Callable[[Dict[str, Any]], bool]]]:
        """
        返回 (predicate, matched_conditions, descriptions, sub_predicates)。
        predicate(case) -> bool；sub_predicates 供 evaluate_with_metadata 逐个求值。
        """
        if condition_str is None or (isinstance(condition_str, float) and pd.isna(condition_str)):
            return _always_true, [], ["无条件"], []
        s = str(condition_str).strip()
        if not s:
            return _always_true, [], ["无条件"], []

        # 整体匹配层（优先）
        for cond in self._whole_str:
            if cond.match(s):
                pred = partial(cond.evaluate, s)
                return pred, [cond], [cond.describe(s)], [pred]

        # 分词层
        tokens = [t.strip() for t in s.split("&") if t.strip()]
        preds: List[Callable[[Dict[str, Any]], bool]] = []
        conds: List[AtomicCondition] = []
        descs: List[str] = []
        for tok in tokens:
            for cond in self._token:
                if cond.match(tok):
                    preds.append(partial(cond.evaluate, tok))
                    conds.append(cond)
                    descs.append(cond.describe(tok))
                    break
            else:
                preds.append(partial(self._unknown.evaluate, tok))
                conds.append(self._unknown)
                descs.append(self._unknown.describe(tok))

        def predicate(case: Dict[str, Any]) -> bool:
            return all(p(case) for p in preds)

        return predicate, conds, descs, preds

    def evaluate(self, condition_str, case: Dict[str, Any]) -> bool:
        pred, _, _, _ = self.parse(condition_str)
        return pred(case)

    def evaluate_with_metadata(self, condition_str, case: Dict[str, Any]) -> Dict[str, Any]:
        """
        返回结构：
        {matched, parsed_condition, overdue_value, atomic_results}
        """
        pred, conds, descs, preds = self.parse(condition_str)
        matched = pred(case)
        overdue_value = parse_overdue_value(case)
        parsed_condition = " & ".join(descs) if descs else "无条件"
        atomic_results = {desc: p(case) for desc, p in zip(descs, preds)}
        return {
            "matched": matched,
            "parsed_condition": parsed_condition,
            "overdue_value": overdue_value,
            "atomic_results": atomic_results,
        }


def _always_true(case: Dict[str, Any]) -> bool:
    return True
