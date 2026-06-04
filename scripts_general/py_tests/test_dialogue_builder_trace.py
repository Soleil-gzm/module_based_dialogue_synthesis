import pytest
import pandas as pd
from unittest.mock import Mock, MagicMock
from core.config import Config
from core.dialogue_builder import DialogueBuilder
from core.condition import KeywordConditionEvaluator
from core.random_service import RandomService
from core.pressure_manager import PressureManager

@pytest.fixture
def mock_config():
    config_dict = {
        "insert_nodes": [],
        "pressure_prob": 0.6,
        "max_repeat": {},
        "goodbye_termination_prob": 0.7
    }
    return Config(config_dict)

@pytest.fixture
def mock_df_dict():
    # 构造一个简单的 DataFrame 用于测试
    df = pd.DataFrame({
        "uid": [1, 2],
        "parent(继承)": [0, 1],
        "repeat(次数)": ["1", "1"],
        "conditions(条件)": ["逾期", "逾期"],
        "human(客户)": ["客户1", "客户2"],
        "assistant(专员)": ["专员1", "专员2"],
        "flexible_stop(可选不继承)": [0, 0],
        "是否再见": [0, 0]
    })
    return {"身份确认": df}

def test_build_trace_no_stop(mock_config, mock_df_dict):
    rng = RandomService(42)
    condition_eval = KeywordConditionEvaluator()
    pressure_manager = PressureManager(pd.DataFrame(), rng)  # 空压力表
    builder = DialogueBuilder(mock_config, mock_df_dict, condition_eval, rng, pressure_manager)

    path = ["身份确认"]
    case = {"抬头": "测试", "客户姓名": "张三"}
    prompt = "test prompt"
    messages, trace = builder.build(path, case, prompt, trace=True)

    assert len(messages) > 0
    assert trace["path"] == path
    assert trace["final_stop_reason"] == "path_natural_end"   # 因为只一个模块且没有再见
    assert len(trace["modules"]) == 1
    module_trace = trace["modules"][0]
    assert module_trace["module"] == "身份确认"
    assert module_trace["status"] == "processed"
    assert module_trace["turn_count"] > 0

def test_build_trace_skip_no_data(mock_config):
    df_dict = {}   # 没有数据
    rng = RandomService(42)
    condition_eval = KeywordConditionEvaluator()
    pressure_manager = PressureManager(pd.DataFrame(), rng)
    builder = DialogueBuilder(mock_config, df_dict, condition_eval, rng, pressure_manager)

    path = ["身份确认"]
    case = {"抬头": "测试"}
    prompt = "test"
    messages, trace = builder.build(path, case, prompt, trace=True)

    # 因为无数据，模块被跳过，messages 只应有 system 消息
    assert len(messages) == 1   # system only
    assert trace["modules"][0]["status"] == "skipped_no_data"
    assert trace["final_stop_reason"] is None   # 没有终止，只是自然结束

# 更多测试：模拟再见触发、条件不匹配、repeat 不匹配等，可以通过构造专门的 DataFrame 实现。