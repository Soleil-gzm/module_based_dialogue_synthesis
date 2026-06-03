'''
Step 3：抽象条件解析器接口
操作：创建 core/condition.py，定义抽象基类 ConditionEvaluator，包含 evaluate(cond_str, case) -> bool 方法。先实现一个简单版本（兼容当前逻辑：只检查是否包含“逾期”）。
原因：将条件判断逻辑从对话生成中抽离，未来可随时替换为更强大的解析器（如 simpleeval），且不影响其他代码。这是依赖倒置的体现。
'''

import pandas as pd
from abc import ABC, abstractmethod
from typing import Dict, Any

class ConditionEvaluator(ABC):
    @abstractmethod
    def evaluate(self, condition_str: str, case: Dict[str, Any]) -> bool:
        pass

class KeywordConditionEvaluator(ConditionEvaluator):
    def evaluate(self, condition_str: str, case: Dict[str, Any]) -> bool:
        if not condition_str or pd.isna(condition_str):
            return True
        return '逾期' in str(condition_str)

# 如果需要更复杂的解析器（如simpleeval），可以后续实现并替换