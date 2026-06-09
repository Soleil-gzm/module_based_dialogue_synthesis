"""
Trace 模块：记录对话生成过程中的路径、模块处理结果、停止原因等。
通过配置文件中的 trace_enabled 开关控制是否记录。
"""

import json
from typing import Any, Dict, List, Optional


class TraceCollector:
    """
    追踪收集器，用于记录单条对话生成过程中的关键决策点。
    使用时采用上下文方式：在生成每条对话前创建实例，生成后调用 to_dict() 获取记录。
    """

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.data: Optional[Dict] = {} if enabled else None

    def start_dialogue(self, path: List[str], case_id: str):
        """开始一条新对话的追踪"""
        if not self.enabled:
            return
        self.data = {
            "path": path.copy(),
            "case_id": case_id,
            "modules": [],
            "final_stop_reason": None,
        }

    def start_module(self, module_name: str, repeat: int) -> Dict:
        """记录开始处理一个模块，返回模块追踪字典（用于后续填充）"""
        if not self.enabled:
            return {}
        module_trace = {
            "module": module_name,
            "repeat": repeat,
            "status": "processed",
            "turn_count": 0,
            "ancestor_count": 0,
            "descendant_count": 0,
            "goodbye_triggered": False,    # 新增
            "goodbye_ignored": False,      # 新增
            "stop_reason": None,
            "error": None,
            "selected_uid": None,
            "pressure_applied": False,
            "pressure_segment_length": 0,
            "pressure_merge_last": False,
        }
        self.data["modules"].append(module_trace)
        return module_trace

    def set_module_status(self, module_trace: Dict, status: str, reason: str = None):
        """设置模块处理状态（跳过原因等）"""
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

    def set_module_ancestors_descendants(
        self, module_trace: Dict, anc_cnt: int, desc_cnt: int
    ):
        if self.enabled:
            module_trace["ancestor_count"] = anc_cnt
            module_trace["descendant_count"] = desc_cnt

    def set_module_pressure(
        self,
        module_trace: Dict,
        applied: bool,
        seg_len: int = 0,
        merge_last: bool = False,
    ):
        if self.enabled:
            module_trace["pressure_applied"] = applied
            module_trace["pressure_segment_length"] = seg_len
            module_trace["pressure_merge_last"] = merge_last

    def set_stop_reason(self, reason: str, module_trace: Dict = None):
        """设置整个对话停止的原因，可关联到某个模块"""
        if not self.enabled:
            return
        self.data["final_stop_reason"] = reason
        if module_trace is not None:
            module_trace["stop_reason"] = reason

    def to_dict(self) -> Dict:
        """返回追踪数据字典，若未启用则返回空字典"""
        return self.data if self.enabled else {}

    def save_to_file(self, filepath: str):
        """将追踪数据保存为 JSON 文件"""
        if self.enabled and self.data:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
