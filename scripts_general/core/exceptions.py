class DialogueGeneratorError(Exception):
    """基础异常类，所有自定义异常的基类"""
    pass


class ConfigError(DialogueGeneratorError):
    """配置错误：配置文件不存在、格式错误、缺少必要配置项等"""
    pass


class DataLoadError(DialogueGeneratorError):
    """数据加载错误：Excel文件读取失败、案例加载失败、概率矩阵加载失败等"""
    pass


class PathGenerationError(DialogueGeneratorError):
    """路径生成错误：路径生成过程中的异常，如无法生成有效路径等"""
    pass


class DialogueBuildError(DialogueGeneratorError):
    """对话构建错误：根据路径构建对话时的异常"""
    pass


class ConditionEvalError(DialogueGeneratorError):
    """条件解析错误：条件表达式解析或评估失败"""
    pass


class PressureManagerError(DialogueGeneratorError):
    """施压管理错误：施压话术获取或应用失败"""
    pass