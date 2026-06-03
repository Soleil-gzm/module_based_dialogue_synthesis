from core.config import Config
from core.condition import ConditionEvaluator, KeywordConditionEvaluator

def create_condition_evaluator(config: Config) -> ConditionEvaluator:
    """工厂方法：根据配置创建条件解析器"""
    parser_type = config.get('condition_parser', 'keyword')
    if parser_type == 'keyword':
        return KeywordConditionEvaluator()
    # 未来可扩展其他类型
    # elif parser_type == 'simple_eval':
    #     return SimpleEvalConditionEvaluator()
    else:
        raise ValueError(f"Unknown condition_parser type: {parser_type}") 