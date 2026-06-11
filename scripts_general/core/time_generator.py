# core/time_generator.py

from abc import ABC, abstractmethod
from typing import Optional

from core.random_service import RandomService


class TimeGenerator(ABC):
    @abstractmethod
    def generate(self, rng: RandomService, base_time: Optional[str] = None) -> str:
        pass


class SimpleNaturalTimeGenerator(TimeGenerator):
    """简单自然时间生成器（完全随机）"""

    def generate(self, rng: RandomService, base_time: Optional[str] = None) -> str:
        period_hours = {
            "上午": (8, 11),
            "中午": (12, 13),
            "下午": (14, 17),
            "晚上": (18, 21),
        }
        period = rng.choice(list(period_hours.keys()))
        low, high = period_hours[period]
        hour = rng.randint(low, high)
        if rng.random() < 0.3:
            minute = rng.choice([15, 30, 45])
            minute_str = f"点{minute}分"
        else:
            minute_str = "点"
        prefix = rng.choice(["今天", "明天", ""])
        if prefix:
            return f"{prefix}{period}{hour}{minute_str}"
        return f"{period}{hour}{minute_str}"


# 可以扩展其他生成器，例如基于查账时间的生成器
# class RelativeTimeGenerator(TimeGenerator): ...
