from core.analyzer import Analyzer, DefaultAnalyzer
from core.case_loader import CaseLoader, DefaultCaseLoader, XiaoyingCaseLoader
from core.condition import ConditionEvaluator, KeywordConditionEvaluator
from core.config import Config
from core.pressure_prob_strategy import (AbsolutePressureStrategy,
                                         LinearDecayPressureStrategy,
                                         NormalizedPressureStrategy,
                                         PressureStrategy,
                                         SigmoidPressureStrategy)
from core.time_generator import SimpleNaturalTimeGenerator, TimeGenerator


def create_condition_evaluator(config: Config) -> ConditionEvaluator:
    """工厂方法：根据配置创建条件解析器"""
    parser_type = config.get("condition_parser", "keyword")
    if parser_type == "keyword":
        return KeywordConditionEvaluator()
    # 未来可扩展其他类型
    # elif parser_type == 'simple_eval':
    #     return SimpleEvalConditionEvaluator()
    else:
        raise ValueError(f"Unknown condition_parser type: {parser_type}")


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


def create_analyzer(config) -> Analyzer:
    """工厂函数：根据配置创建分析器"""
    analyzer_cfg = config.get("analyzer", {})
    ana_type = analyzer_cfg.get("type", "default")
    if ana_type == "default":
        fmt = analyzer_cfg.get("format", "html")

        # 将配置中的压力参数键名映射为 DefaultAnalyzer 期望的简化键名
        pressure_config = {}
        key_mapping = {
            "pressure_start_prob": "start_prob",
            "pressure_end_prob": "end_prob",
            "pressure_curve_exponent": "exponent",
            "pressure_max_total": "max_total",
            "pressure_position_mode": "mode",
        }
        for cfg_key, simple_key in key_mapping.items():
            value = config.get(cfg_key)
            if value is not None:
                pressure_config[simple_key] = value

        return DefaultAnalyzer(format=fmt, pressure_config=pressure_config)
    else:
        raise ValueError(f"Unknown analyzer type: {ana_type}")


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
