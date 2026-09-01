from core.analyzer import DefaultAnalyzer
from core.case_loader import CaseLoader, DefaultCaseLoader, XiaoyingCaseLoader
from core.config import Config
from core.pressure_prob_strategy import (AbsolutePressureStrategy,
                                         LinearDecayPressureStrategy,
                                         NormalizedPressureStrategy,
                                         PressureStrategy,
                                         SigmoidPressureStrategy)
from core.time_generator import SimpleNaturalTimeGenerator, TimeGenerator
from core.probability import ProbabilityCalculator,ExponentialProbabilityCalculator,SigmoidProbabilityCalculator,LinearProbabilityCalculator


def create_case_loader(config: Config) -> CaseLoader:
    """根据配置创建案例加载器"""
    loader_type = config.get("case_loader.type", "default")
    if loader_type == "default":
        cases_dir = config.get("cases_dir")
        if not cases_dir:
            raise ValueError("默认加载器需要配置 cases_dir")
        return DefaultCaseLoader(cases_dir)
    elif loader_type == "xiaoying":
        replace_dir = config.get("case_loader.replace_dir")
        system_dir = config.get("case_loader.system_dir")
        if not replace_dir or not system_dir:
            raise ValueError(
                "小赢加载器需要配置 case_loader.replace_dir 和 case_loader.system_dir"
            )
        return XiaoyingCaseLoader(replace_dir, system_dir)
    else:
        raise ValueError(f"Unknown case_loader type: {loader_type}")


def create_time_generator(config: Config) -> TimeGenerator:
    """工厂方法：根据配置创建随机时间占用符时间生成器"""
    gen_type = config.get("time_generator.type", "simple_natural")
    if gen_type == "simple_natural":
        return SimpleNaturalTimeGenerator()
    # 未来可扩展其他类型
    # elif gen_type == "relative":
    #     return RelativeTimeGenerator()
    else:
        raise ValueError(f"Unknown time_generator type: {gen_type}")



def create_pressure_strategy(config) -> PressureStrategy:
    """根据配置创建压力策略实例"""
    strategy_type = config.get("pressure_strategy", {}).get("type", "normalized")
    if strategy_type == "normalized":
        return NormalizedPressureStrategy()
    elif strategy_type == "absolute":
        max_expected = config.get("max_expected_modules", 15)
        return AbsolutePressureStrategy(max_expected_modules=max_expected)
    elif strategy_type == "sigmoid":
        slope = config.get("pressure_strategy", {}).get("slope", 10.0)
        return SigmoidPressureStrategy(slope=slope)
    elif strategy_type == "linear_decay":
        return LinearDecayPressureStrategy()
    else:
        raise ValueError(f"Unknown pressure strategy type: {strategy_type}")

def create_probability_calculator(config: Config, prefix: str) -> ProbabilityCalculator:
    """
    根据配置前缀创建概率计算器。
    :param config: 配置对象
    :param prefix: 配置前缀，如 'pressure' 或 'goodbye'
    :return: ProbabilityCalculator 实例
    """
    calc_type = config.get(f"{prefix}_calc_type", "exponential")
    if calc_type == "exponential":
        start = config.get(f"{prefix}_start_prob", 0.0)
        end = config.get(f"{prefix}_end_prob", 1.0)
        exponent = config.get(f"{prefix}_exponent", 1.0)
        return ExponentialProbabilityCalculator(start, end, exponent)
    elif calc_type == "sigmoid":
        slope = config.get(f"{prefix}_sigmoid_slope", 10.0)
        return SigmoidProbabilityCalculator(slope)
    elif calc_type == "linear":
        start = config.get(f"{prefix}_start_prob", 0.0)
        end = config.get(f"{prefix}_end_prob", 1.0)
        return LinearProbabilityCalculator(start, end)
    else:
        raise ValueError(f"Unknown probability calculator type: {calc_type}")