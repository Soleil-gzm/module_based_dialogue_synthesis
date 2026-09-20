import random
from typing import Any, List, Optional

import numpy as np


class RandomService:
    """统一的随机服务，封装 random 和 numpy 随机，支持种子注入和测试"""

    def __init__(self, seed: Optional[int] = None):
        self._random = random.Random(
            seed
        )  # 创建独立的 Python 随机生成器，避免全局污染，支持可重复随机
        if seed is not None:
            np.random.seed(
                seed
            )  # 同步设置 numpy 的全局随机种子，确保 np_choice 等方法也可重复
        self._seed = seed

    def random(self) -> float:
        """返回 [0.0, 1.0) 之间的随机浮点数"""
        return self._random.random()

    def choice(self, seq: List[Any]) -> Any:
        """从序列中随机选择一个元素"""
        return self._random.choice(seq)

    def choices(self, seq: List[Any], k: int) -> List[Any]:
        """随机选择多个元素（可重复）"""
        return self._random.choices(seq, k=k)

    def randint(self, a: int, b: int) -> int:
        """返回 [a, b] 之间的随机整数"""
        return self._random.randint(a, b)

    def uniform(self, a: float, b: float) -> float:
        """返回 [a, b) 之间的随机浮点数"""
        return self._random.uniform(a, b)  # 用于随机金额生成，需要修改

    def sample(self, seq: List[Any], k: int) -> List[Any]:
        """不放回抽样"""
        return self._random.sample(seq, k)

    def shuffle(
        self, seq: List[Any]
    ) -> None:  # 当前未使用。可用于随机化候选顺序，增加多样性。
        """打乱列表"""
        self._random.shuffle(seq)

    def np_choice(self, a: np.ndarray, p: Optional[np.ndarray] = None) -> Any:
        """使用 numpy 随机选择（基于当前 numpy 种子）"""
        return np.random.choice(a, p=p)
