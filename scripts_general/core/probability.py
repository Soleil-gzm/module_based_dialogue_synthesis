"""
概率计算器：基于归一化位置 t 计算动态概率。
支持多种曲线（指数、Sigmoid、线性等），通过配置选择。
"""

import math
from abc import ABC, abstractmethod

from core.config import Config


class ProbabilityCalculator(ABC):
    @abstractmethod
    def calculate(self, t: float) -> float:
        """
        根据归一化位置 t (0~1) 计算概率值。
        :param t: 归一化位置，范围 [0, 1]
        :return: 概率值，范围 [0, 1]
        """
        pass


class ExponentialProbabilityCalculator(ProbabilityCalculator):
    """指数曲线：prob = start + (end - start) * t^exponent"""
    def __init__(self, start_prob: float, end_prob: float, exponent: float):
        self.start_prob = max(0.0, min(1.0, start_prob))
        self.end_prob = max(0.0, min(1.0, end_prob))
        self.exponent = exponent

    def calculate(self, t: float) -> float:
        t = max(0.0, min(1.0, t))
        prob = self.start_prob + (self.end_prob - self.start_prob) * (t ** self.exponent)
        return max(0.0, min(1.0, prob))


class SigmoidProbabilityCalculator(ProbabilityCalculator):
    """Sigmoid 曲线：prob = 1 / (1 + exp(-slope * (t - 0.5)))"""
    def __init__(self, slope: float = 10.0):
        self.slope = slope

    def calculate(self, t: float) -> float:
        t = max(0.0, min(1.0, t))
        prob = 1.0 / (1.0 + math.exp(-self.slope * (t - 0.5)))
        return prob


class LinearProbabilityCalculator(ProbabilityCalculator):
    """线性曲线：prob = start + (end - start) * t"""
    def __init__(self, start_prob: float, end_prob: float):
        self.start_prob = max(0.0, min(1.0, start_prob))
        self.end_prob = max(0.0, min(1.0, end_prob))

    def calculate(self, t: float) -> float:
        t = max(0.0, min(1.0, t))
        prob = self.start_prob + (self.end_prob - self.start_prob) * t
        return max(0.0, min(1.0, prob))


