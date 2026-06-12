"""
施压概率策略模块：根据配置选择不同的 t 值计算方法，用于动态概率计算。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

import numpy as np


class PressureStrategy(ABC):
    """施压概率策略抽象基类"""

    @abstractmethod
    def get_normalized_position(self, idx: int, total: int, **kwargs) -> float:
        """
        返回归一化位置 t (0~1)，用于概率公式：prob = start + (end-start)*t^exponent
        :param idx: 当前模块在路径中的索引（从0开始）
        :param total: 路径总模块数
        :param kwargs: 策略所需的额外参数（如 max_expected_modules）
        """
        pass


class NormalizedPressureStrategy(PressureStrategy):
    """归一化策略：t = idx / (total-1)"""

    def get_normalized_position(self, idx: int, total: int, **kwargs) -> float:
        if total <= 1:
            return 0.0
        return idx / (total - 1)


class AbsolutePressureStrategy(PressureStrategy):
    """绝对索引策略：t = min(1.0, idx / max_expected_modules)"""

    def __init__(self, max_expected_modules: int = 15):
        self.max_expected_modules = max_expected_modules

    def get_normalized_position(self, idx: int, total: int, **kwargs) -> float:
        return min(1.0, idx / self.max_expected_modules)


class SigmoidPressureStrategy(PressureStrategy):
    """
    Sigmoid 曲线策略：t = 1/(1+exp(-k * (idx/(total-1) - 0.5)))
    其中 k 为斜率，默认 10。
    """

    def __init__(self, slope: float = 10.0):
        self.slope = slope

    def get_normalized_position(self, idx: int, total: int, **kwargs) -> float:
        if total <= 1:
            return 0.0
        x = idx / (total - 1)  # 原始归一化位置
        # Sigmoid 中心在 0.5
        t = 1.0 / (1.0 + np.exp(-self.slope * (x - 0.5)))
        return t


class LinearDecayPressureStrategy(PressureStrategy):
    """线性衰减策略：t = 1 - idx/(total-1)（越往后概率越低）"""

    def get_normalized_position(self, idx: int, total: int, **kwargs) -> float:
        if total <= 1:
            return 1.0
        return 1.0 - idx / (total - 1)
