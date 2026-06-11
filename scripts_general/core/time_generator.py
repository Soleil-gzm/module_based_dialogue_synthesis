"""
时间生成器模块：将机械的“查账时间过后X小时”替换为自然口语化表达。
提供抽象基类及默认的简单自然时间生成器。
"""

from abc import ABC, abstractmethod
from typing import Optional

from core.random_service import RandomService


class TimeGenerator(ABC):
    """时间生成器抽象接口"""

    @abstractmethod
    def generate(self, rng: RandomService, base_time: Optional[str] = None) -> str:
        """
        生成一个自然口语化的时间字符串
        :param rng: 随机服务
        :param base_time: 可选的参考时间（如案例中的“查账时间”），目前简单实现中忽略此参数
        :return: 类似 “今天上午10点” 或 “明天下午2点半” 的字符串
        """
        pass


class SimpleNaturalTimeGenerator(TimeGenerator):
    """
    简单自然时间生成器：
    - 完全随机生成今天/明天 + 时段 + 小时（+分钟可选）
    - 不依赖 base_time，保证生成表达自然流畅
    """

    def generate(self, rng: RandomService, base_time: Optional[str] = None) -> str:
        # 时段及对应合理小时范围
        period_hours = {
            "上午": (8, 11),
            "中午": (12, 13),
            "下午": (14, 17),
            "晚上": (18, 21),
        }
        period = rng.choice(list(period_hours.keys()))
        low, high = period_hours[period]
        hour = rng.randint(low, high)

        # 分钟：0, 15, 30, 45 可选，但为了简洁，30%概率不加分钟
        if rng.random() < 0.3:
            minute = rng.choice([15, 30, 45])
            minute_str = f"点{minute}分"
        else:
            minute_str = "点"

        # 日期前缀：今天 / 明天 / 空
        prefix = rng.choice(["今天", "明天", ""])
        if prefix:
            return f"{prefix}{period}{hour}{minute_str}"
        else:
            return f"{period}{hour}{minute_str}"


# 可选的扩展生成器（基于查账时间增加4-6小时），暂不实现，按需添加