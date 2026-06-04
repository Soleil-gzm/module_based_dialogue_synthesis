import pytest
from core.condition import KeywordConditionEvaluator
from core.random_service import RandomService  # 未使用但占位


def test_keyword_evaluator():
    evaluator = KeywordConditionEvaluator()
    case = {"客户性别": "先生", "逾期笔数": 2}

    # 包含“逾期”应该返回 True
    assert evaluator.evaluate("逾期30天", case) is True
    # 不包含“逾期”应该返回 False
    assert evaluator.evaluate("正常还款", case) is False
    # 空字符串应返回 True（兼容旧逻辑）
    assert evaluator.evaluate("", case) is True
    # NaN 应返回 True
    import pandas as pd

    assert evaluator.evaluate(pd.NA, case) is True
