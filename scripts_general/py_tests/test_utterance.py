import pandas as pd
import pytest
from core.utterance import sample_utterance, get_ancestors, get_random_descendant_chain, fill_placeholders
from core.random_service import RandomService

def test_sample_utterance():
    rng = RandomService(42)
    data = {
        "human(客户)": "你好/您好",
        "assistant(专员)": "我是专员"
    }
    row = pd.Series(data)
    assert sample_utterance(row, True, rng) in ["你好", "您好"]
    assert sample_utterance(row, False, rng) == "我是专员"
    
    # 空值处理
    empty_row = pd.Series({"human(客户)": None})
    assert sample_utterance(empty_row, True, rng) == ""

def test_fill_placeholders():
    case = {"客户姓名": "张三", "逾期金额": "8000"}
    text = "尊敬的{客户姓名}，您的逾期金额是{逾期金额}元。"
    result = fill_placeholders(text, case)
    assert result == "尊敬的张三，您的逾期金额是8000元。"
    
    # 不存在的占位符保留原样
    text2 = "测试{不存在}"
    assert fill_placeholders(text2, case) == "测试{不存在}"