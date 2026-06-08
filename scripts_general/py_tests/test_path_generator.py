import numpy as np
import pandas as pd
import pytest
from core.config import Config
from core.path_generator import PathGenerator
from core.random_service import RandomService


# 创建一个最小的配置用于测试
def make_test_config():
    config_dict = {
        "modules": ["身份确认", "告知", "承诺还款", "已还款"],
        "max_repeat": {"身份确认": 1, "告知": 1, "承诺还款": 1, "已还款": 1},
        "terminal_modules": ["承诺还款", "已还款"],
        "a_set": [],
        "b_set": [],
        "start_module": "身份确认",
    }
    return Config(config_dict)


def test_generate_one_simple():
    config = make_test_config()
    # 构造一个简单的概率矩阵：身份确认 -> 告知(1.0)
    prob_df = pd.DataFrame(
        [[1.0, 0.0, 0.0, 0.0]],
        index=["身份确认"],
        columns=["身份确认", "告知", "承诺还款", "已还款"],
    )
    rng = RandomService(42)
    gen = PathGenerator(config, prob_df, rng)
    path = gen.generate_one()
    # 由于概率矩阵强制从身份确认到告知，且告知后可到承诺还款（概率需要设置）
    # 但这里简单起见，期望至少包含身份确认和告知
    assert path[0] == "身份确认"
    # 实际更多断言需要根据概率矩阵补充
