from core.case_loader import CaseLoader, DefaultCaseLoader, XiaoyingCaseLoader
from core.condition import ConditionEvaluator, KeywordConditionEvaluator
from core.config import Config


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
        raise ValueError(f"未知的 case_loader 类型: {loader_type}")
