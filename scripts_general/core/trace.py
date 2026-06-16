"""
Trace 模块：记录对话生成过程中的路径、模块处理结果、停止原因等。
通过配置文件中的 trace_enabled 开关控制是否记录。
"""

import json
import numpy as np
from typing import Any, Dict, List, Optional


def _convert_to_native(obj: Any) -> Any:
    """递归将 numpy 类型转换为 Python 原生类型，确保 JSON 可序列化"""
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return [_convert_to_native(item) for item in obj.tolist()]
    elif isinstance(obj, dict):
        return {k: _convert_to_native(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_convert_to_native(item) for item in obj]
    else:
        return obj


class TraceCollector:
    """
    追踪收集器，用于记录单条对话生成过程中的关键决策点。
    使用时采用上下文方式：在生成每条对话前创建实例，生成后调用 to_dict() 获取记录。
    """

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.data: Optional[Dict] = {} if enabled else None

    # ---------- 对话级 ----------
    def start_dialogue(self, path: List[str], case_id: str):
        """开始一条新对话的追踪"""
        if not self.enabled:
            return
        self.data = {
            "path": path.copy(),
            "case_id": case_id,
            "total_turns": 0,
            "total_pressure_turns": 0,
            "overall_stop_reason": None,
            "modules": [],
        }

    def set_dialogue_summary(self, total_turns: int, total_pressure_turns: int):
        if not self.enabled:
            return
        self.data["total_turns"] = total_turns
        self.data["total_pressure_turns"] = total_pressure_turns

    def set_stop_reason(self, reason: str, module_trace: Dict = None):
        if not self.enabled:
            return
        self.data["overall_stop_reason"] = reason
        if module_trace is not None:
            module_trace["stop_reason"] = reason

    def set_module_flexible_value(self, module_trace: Dict, value: int):
        """记录 flexible_stop(可选不继承) 列的原始数值（0/1）"""
        if self.enabled:
            module_trace["utterance"]["flexible_value"] = value

    def set_module_goodbye_value(self, module_trace: Dict, value: int):
        """记录“是否再见”列的原始数值（0/1）"""
        if self.enabled:
            module_trace["goodbye"]["goodbye_value"] = value

    # ---------- 模块级 ----------
    def start_module(self, module_name: str, repeat: int) -> Dict:
        if not self.enabled:
            return {}
        module_trace = {
            "module": module_name,
            "repeat": repeat,
            "status": "processed",
            "selected_uid": None,
            "turn_count": 0,
            "utterance": {
                "ancestor_count": 0,
                "descendant_count": 0,
                "ancestor_uids": [],  # 新增：祖先 UID 列表（顺序：从根到当前）
                "descendant_uids": [],  # 新增：后代 UID 列表（顺序：从上到下）
                "parent_raw": None,  # 新增：# 原始 parent(继承) 值（字符串，可能包含 /）
                "flexible_stop_triggered": False,
                "flexible_value": None,  # 新增：记录 flexible_stop(可选不继承) 原始值
            },
            "goodbye": {
                "goodbye_triggered": False,
                "goodbye_ignored": False,
                "goodbye_value": None,  # 新增：记录“是否再见”原始值
            },
            "pressure": {
                "applied": False,
                "pass": False,
                "prob_used": None,
                "merge_last": False,
                "turn_count": 0,
                "flexible_triggered_in_pressure": False,
            },
            "stop_reason": None,
            "error": None,
        }
        self.data["modules"].append(module_trace)
        return module_trace

    def set_module_status(self, module_trace: Dict, status: str, reason: str = None):
        if not self.enabled:
            return
        module_trace["status"] = status
        if reason:
            module_trace["stop_reason"] = reason

    def set_module_selected_uid(self, module_trace: Dict, uid: int):
        if self.enabled:
            module_trace["selected_uid"] = uid

    def set_module_turn_count(self, module_trace: Dict, turn_count: int):
        if self.enabled:
            module_trace["turn_count"] = turn_count

    # utterance 子对象
    def set_module_utterance_chain(
        self,
        module_trace: Dict,
        ancestor_uids: List[int],
        descendant_uids: List[int],
        parent_raw: Any = None,
    ):
        if not self.enabled:
            return
        module_trace["utterance"]["ancestor_count"] = len(ancestor_uids)
        module_trace["utterance"]["descendant_count"] = len(descendant_uids)
        module_trace["utterance"]["ancestor_uids"] = ancestor_uids
        module_trace["utterance"]["descendant_uids"] = descendant_uids
        if parent_raw is not None:
            module_trace["utterance"]["parent_raw"] = parent_raw

    def set_module_flexible_stop(self, module_trace: Dict, triggered: bool):
        if self.enabled:
            module_trace["utterance"]["flexible_stop_triggered"] = triggered

    # goodbye 子对象
    def set_module_goodbye(self, module_trace: Dict, triggered: bool, ignored: bool):
        if self.enabled:
            module_trace["goodbye"]["goodbye_triggered"] = triggered
            module_trace["goodbye"]["goodbye_ignored"] = ignored

    # pressure 子对象
    def set_module_pressure(
        self,
        module_trace: Dict,
        applied: bool,
        pass_: bool = False,
        prob_used: float = None,
        merge_last: bool = False,
        turn_count: int = 0,
        flexible_triggered_in_pressure: bool = False,
    ):
        if not self.enabled:
            return
        module_trace["pressure"]["applied"] = applied
        module_trace["pressure"]["pass"] = pass_
        module_trace["pressure"]["prob_used"] = prob_used
        module_trace["pressure"]["merge_last"] = merge_last
        module_trace["pressure"]["turn_count"] = turn_count
        module_trace["pressure"][
            "flexible_triggered_in_pressure"
        ] = flexible_triggered_in_pressure

    # 其他
    def to_dict(self) -> Dict:
        """返回追踪数据字典，若未启用则返回空字典；自动转换 numpy 类型"""
        if not self.enabled or self.data is None:
            return {}
        return _convert_to_native(self.data)

    def save_to_file(self, filepath: str):
        if self.enabled and self.data:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
