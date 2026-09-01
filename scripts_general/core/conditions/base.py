"""条件评估器抽象基类。"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class ConditionEvaluator(ABC):
    @abstractmethod
    def evaluate(self, condition_str: str, case: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    def evaluate_with_metadata(self, condition_str: str, case: Dict[str, Any]) -> Dict[str, Any]:
        pass
