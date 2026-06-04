import pytest
from unittest.mock import Mock, MagicMock
import pandas as pd
from core.config import Config
from core.dialogue_builder import DialogueBuilder
from core.condition import ConditionEvaluator
from core.random_service import RandomService
from core.pressure_manager import PressureManager

def test_build_without_pressure():
    # 创建 mock 对象
    config = Mock(spec=Config)
    config.get.side_effect = lambda key, default=None: {
        'insert_nodes': [],
        'pressure_prob': 0.6,
        'max_repeat': {}
    }.get(key, default)
    
    df_dict = {}  # 简化，实际需要构造包含模块的DataFrame
    condition_evaluator = Mock(spec=ConditionEvaluator)
    condition_evaluator.evaluate.return_value = True
    rng = RandomService(42)
    pressure_manager = Mock(spec=PressureManager)
    pressure_manager.get_pressure_segment.return_value = ([], False)
    
    builder = DialogueBuilder(config, df_dict, condition_evaluator, rng, pressure_manager)
    
    # 构造一个最简单的路径和案例
    path = ["身份确认"]
    case = {"抬头": "催收部"}
    prompt = "测试prompt"
    
    # 由于 df_dict 为空，应跳过模块，最终只会有 system 消息
    messages = builder.build(path, case, prompt)
    assert len(messages) == 1
    assert messages[0]["role"] == "system"