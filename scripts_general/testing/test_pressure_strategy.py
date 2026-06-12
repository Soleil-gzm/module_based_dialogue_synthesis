"""
单元测试：施压概率策略模块 (core.pressure_strategy)
"""

import pytest
from core.config import Config
from core.factory import create_pressure_strategy
from core.pressure_prob_strategy import (AbsolutePressureStrategy,
                                         LinearDecayPressureStrategy,
                                         NormalizedPressureStrategy,
                                         SigmoidPressureStrategy)


class TestPressureStrategies:
    """测试各个策略的 get_normalized_position 方法"""

    def test_normalized_strategy(self):
        strategy = NormalizedPressureStrategy()
        # total=1: 返回 0.0
        assert strategy.get_normalized_position(idx=0, total=1) == 0.0
        # normal case
        assert strategy.get_normalized_position(idx=0, total=4) == 0.0
        assert strategy.get_normalized_position(idx=1, total=4) == 1 / 3
        assert strategy.get_normalized_position(idx=2, total=4) == 2 / 3
        assert strategy.get_normalized_position(idx=3, total=4) == 1.0

    def test_absolute_strategy_default(self):
        strategy = AbsolutePressureStrategy(max_expected_modules=10)
        # idx 小于 max_expected
        assert strategy.get_normalized_position(idx=0, total=5) == 0.0
        assert strategy.get_normalized_position(idx=3, total=5) == 0.3
        assert strategy.get_normalized_position(idx=9, total=5) == 0.9
        # idx 达到 max_expected
        assert strategy.get_normalized_position(idx=10, total=5) == 1.0
        assert strategy.get_normalized_position(idx=15, total=5) == 1.0

    def test_absolute_strategy_custom_max(self):
        strategy = AbsolutePressureStrategy(max_expected_modules=7)
        assert strategy.get_normalized_position(idx=0, total=3) == 0.0
        assert strategy.get_normalized_position(idx=4, total=3) == 4 / 7
        assert strategy.get_normalized_position(idx=7, total=3) == 1.0
        assert strategy.get_normalized_position(idx=10, total=3) == 1.0

    def test_sigmoid_strategy(self):
        strategy = SigmoidPressureStrategy(slope=10.0)
        # total=1: 返回 0.0
        assert strategy.get_normalized_position(idx=0, total=1) == 0.0
        # 对称中心在 0.5
        # 当 idx=0, x=0 => t ≈ 1/(1+exp(5)) ≈ 0.0067
        t0 = strategy.get_normalized_position(idx=0, total=10)
        assert 0.0 < t0 < 0.01
        # 当 idx= total-1, x=1 => t ≈ 1/(1+exp(-5)) ≈ 0.9933
        t_last = strategy.get_normalized_position(idx=9, total=10)
        assert 0.99 < t_last < 1.0
        # 中心点: idx=4.5 (但整数索引 4 或 5 接近 0.5)
        t_mid = strategy.get_normalized_position(idx=4, total=10)  # x=4/9≈0.444
        # 应接近 0.5 但略小于
        assert 0.35 < t_mid < 0.38

    # def test_backward_compatibility_absolute(self):
    #     config = Config({
    #         "pressure_position_mode": "absolute",
    #         "max_expected_modules": 10
    #     })
    #     strategy = create_pressure_strategy(config)
    #     assert isinstance(strategy, AbsolutePressureStrategy)
    #     # 可选：验证 max_expected_modules 是否正确传递
    #     assert strategy.max_expected_modules == 10

    def test_sigmoid_strategy_custom_slope(self):
        strategy = SigmoidPressureStrategy(slope=2.0)
        t0 = strategy.get_normalized_position(idx=0, total=10)
        # 较缓的斜率，t0 应该比斜率为10时更接近 0.5
        assert 0.1 < t0 < 0.4

    def test_linear_decay_strategy(self):
        strategy = LinearDecayPressureStrategy()
        # total=1: 返回 1.0
        assert strategy.get_normalized_position(idx=0, total=1) == 1.0
        # normal
        assert strategy.get_normalized_position(idx=0, total=4) == 1.0
        assert strategy.get_normalized_position(idx=1, total=4) == 1 - 1 / 3
        assert strategy.get_normalized_position(idx=2, total=4) == 1 - 2 / 3
        assert strategy.get_normalized_position(idx=3, total=4) == 0.0


class TestCreatePressureStrategy:
    """测试工厂函数"""

    def test_create_normalized_from_new_config(self):
        config = Config({"pressure_strategy": {"type": "normalized"}})
        strategy = create_pressure_strategy(config)
        assert isinstance(strategy, NormalizedPressureStrategy)

    def test_create_absolute_from_new_config(self):
        config = Config(
            {"pressure_strategy": {"type": "absolute"}, "max_expected_modules": 12}
        )
        strategy = create_pressure_strategy(config)
        assert isinstance(strategy, AbsolutePressureStrategy)
        assert strategy.max_expected_modules == 12

    def test_create_sigmoid_from_new_config(self):
        config = Config({"pressure_strategy": {"type": "sigmoid", "slope": 8.0}})
        strategy = create_pressure_strategy(config)
        assert isinstance(strategy, SigmoidPressureStrategy)
        assert strategy.slope == 8.0

    def test_create_linear_decay_from_new_config(self):
        config = Config({"pressure_strategy": {"type": "linear_decay"}})
        strategy = create_pressure_strategy(config)
        assert isinstance(strategy, LinearDecayPressureStrategy)

    def test_backward_compatibility_normalized(self):
        # 旧配置：pressure_position_mode = "normalized"
        config = Config({"pressure_position_mode": "normalized"})
        strategy = create_pressure_strategy(config)
        assert isinstance(strategy, NormalizedPressureStrategy)

    def test_backward_compatibility_absolute(self):
        config = Config(
            {"pressure_position_mode": "absolute", "max_expected_modules": 10}
        )
        strategy = create_pressure_strategy(config)
        assert isinstance(strategy, AbsolutePressureStrategy)
        assert strategy.max_expected_modules == 10

    def test_backward_compatibility_default(self):
        # 无任何配置，默认归一化
        config = Config({})
        strategy = create_pressure_strategy(config)
        assert isinstance(strategy, NormalizedPressureStrategy)

    def test_unknown_strategy_raises(self):
        config = Config({"pressure_strategy": {"type": "unknown"}})
        with pytest.raises(ValueError, match="Unknown pressure strategy type"):
            create_pressure_strategy(config)
