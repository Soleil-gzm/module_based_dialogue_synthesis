import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from core.condition import ConditionEvaluator
from core.config import Config
from core.pressure_manager import PressureManager
from core.random_service import RandomService
from core.trace import TraceCollector
from core.utterance import (fill_placeholders, get_ancestors,
                            get_random_descendant_chain, sample_utterance)


class DialogueBuilder:
    """根据模块路径生成完整对话"""

    def __init__(
        self,
        config: Config,
        df_dict: Dict[str, pd.DataFrame],
        condition_evaluator: ConditionEvaluator,
        rng: RandomService,
        pressure_manager: PressureManager,
        logger: logging.Logger = None,
    ):
        self.config = config
        self.df_dict = df_dict
        self.condition_evaluator = condition_evaluator
        self.rng = rng
        self.pressure_manager = pressure_manager
        self.logger = logger or logging.getLogger("DialogueBuilder")
        self.insert_nodes = set(config.get("insert_nodes", []))
        self.pressure_prob = config.get("pressure_prob", 0.6)  # 保留兼容旧配置
        self.max_repeat = config.get("max_repeat", {})
        self.goodbye_termination_prob = config.get("goodbye_termination_prob", 0.7)
        self.trace_enabled = config.get("trace_enabled", False)
        self.trace_collector = TraceCollector(self.trace_enabled)

        # 动态施压话术配置
        self.pressure_dynamic_enabled = config.get("pressure_dynamic_enabled", True)
        self.pressure_start_prob = config.get("pressure_start_prob", 0.05)
        self.pressure_end_prob = config.get("pressure_end_prob", 0.5)
        self.pressure_curve_exponent = config.get("pressure_curve_exponent", 2.0)
        self.pressure_max_total = config.get("pressure_max_total", 3)
        self.module_pressure_weights = config.get("module_pressure_weights", {})
        # 施压概率位置模式
        self.pressure_position_mode = config.get("pressure_position_mode", "normalized")  # "normalized" 或 "absolute"
        self.max_expected_modules = config.get("max_expected_modules", 15)  # 绝对模式下期望的最大模块数

        # 辅助变量（每次 build 时重置）
        self.pressure_count = 0

    def _should_terminate(
        self, row: pd.Series, repeat: int, node: str, module_trace: Dict = None
    ) -> bool:
        """检查是否因再见标志而终止（包含概率控制），并记录 trace"""
        if row.get("是否再见") == 1 and repeat <= self.max_repeat.get(node, 999):
            if self.rng.random() <= self.goodbye_termination_prob:
                self.logger.debug(f"模块 {node} repeat={repeat} 再见触发，终止对话")
                if module_trace:
                    module_trace["goodbye_triggered"] = True
                    module_trace["goodbye_ignored"] = False
                return True
            else:
                self.logger.debug(
                    f"模块 {node} repeat={repeat} 再见被忽略（概率不触发），继续对话"
                )
                if module_trace:
                    module_trace["goodbye_triggered"] = False
                    module_trace["goodbye_ignored"] = True
        return False

    def _append_segment(
        self,
        messages: List[Dict],
        segment: List[Dict[str, str]],
        merge_last: bool = False,
    ) -> None:
        """将施压话术片段追加到对话消息列表中
            Args:
        messages: 当前对话消息列表（会被原地修改）
        segment: 话术片段，每个元素为 {"user": str, "assistant": str}
        merge_last: 是否将片段的第一条 assistant 合并到上一条 assistant 消息中
        """
        if not segment:
            return

        if merge_last and messages and messages[-1].get("role") == "assistant":
            # 合并第一条 assistant 到上一轮
            messages[-1]["content"] += segment[0]["assistant"]
            remaining = segment[1:]
        else:
            remaining = segment

        for item in remaining:
            if item.get("user"):
                messages.append({"role": "user", "content": item["user"]})
            if item.get("assistant"):
                messages.append(
                    {"role": "assistant", "content": item["assistant"], "loss": "True"}
                )

    def _process_module(
        self,
        node: str,
        repeat: int,
        case: Dict[str, Any],
        messages: List[Dict],
        node_counts: Dict[str, int],
    ) -> Tuple[bool, str]:
        """处理单个模块的话术选择和对话追加。返回 (stop_dialogue, stop_reason)
        stop_dialogue: 是否应该终止整个对话
        stop_reason: 终止原因（仅在 stop_dialogue=True 时有意义）
        """
        df_node = self.df_dict.get(node)
        if df_node is None or df_node.empty:
            self.logger.debug(f"模块 {node} 无数据，跳过")
            self.trace_collector.set_module_status(
                self._current_module_trace, "skipped_no_data"
            )
            return False, ""

        # 筛选 repeat 匹配的行
        mask = df_node["repeat(次数)"].apply(
            lambda x: str(repeat) in str(x).split("/") if pd.notna(x) else False
        )
        candidates = df_node[mask]
        if candidates.empty:
            self.logger.debug(f"模块 {node} repeat={repeat} 无候选行")
            self.trace_collector.set_module_status(
                self._current_module_trace, "skipped_no_repeat_match"
            )
            return False, ""

        # 根据条件筛选
        valid_rows = []
        for _, row in candidates.iterrows():
            cond_str = row.get("conditions(条件)", "")
            if self.condition_evaluator.evaluate(cond_str, case):
                valid_rows.append(row)
        if not valid_rows:
            self.logger.debug(f"模块 {node} repeat={repeat} 无满足条件的行")
            self.trace_collector.set_module_status(
                self._current_module_trace, "skipped_condition_mismatch"
            )
            return False, ""

        row = self.rng.choice(valid_rows)
        self.trace_collector.set_module_selected_uid(
            self._current_module_trace, row["uid"]
        )

        # 获得前后继承链
        ancestors = get_ancestors(row["uid"], df_node)
        descendant_chain = get_random_descendant_chain(
            row["uid"],
            df_node,
            self.rng,
            flexible_stop_prob=self.config.get("flexible_stop_prob", 0.3),
        )

        turn_list = []
        stop_reason = ""

        # --- 辅助函数：将 turn_list 提交到 messages ---
        def flush_turn_list():
            for user_txt, assistant_txt in turn_list:
                if user_txt:
                    messages.append({"role": "user", "content": user_txt})
                if assistant_txt:
                    messages.append(
                        {"role": "assistant", "content": assistant_txt, "loss": "True"}
                    )

        # 祖先链
        for anc in ancestors:
            user_txt = sample_utterance(anc, True, self.rng)
            assistant_txt = sample_utterance(anc, False, self.rng)
            if user_txt or assistant_txt:
                turn_list.append((user_txt, assistant_txt))
            if self._should_terminate(anc, repeat, node, self._current_module_trace):
                # 触发再见：先提交已收集的话术（包括这一轮），然后停止
                flush_turn_list()  # 确保再见前保存当前对话
                stop_reason = f"goodbye_in_ancestor_{anc['uid']}"
                self.trace_collector.set_stop_reason(
                    stop_reason, self._current_module_trace
                )
                self.trace_collector.set_module_turn_count(
                    self._current_module_trace, len(turn_list)
                )
                return True, stop_reason

        # 当前行
        current_user = sample_utterance(row, True, self.rng)
        current_assistant = sample_utterance(row, False, self.rng)
        turn_list.append((current_user, current_assistant))
        if self._should_terminate(row, repeat, node, self._current_module_trace):
            flush_turn_list()
            stop_reason = f"goodbye_in_current_{row['uid']}"
            self.trace_collector.set_stop_reason(
                stop_reason, self._current_module_trace
            )
            self.trace_collector.set_module_turn_count(
                self._current_module_trace, len(turn_list)
            )
            return True, stop_reason

        # 后代链
        for desc in descendant_chain:
            user_txt = sample_utterance(desc, True, self.rng)
            assistant_txt = sample_utterance(desc, False, self.rng)
            if user_txt or assistant_txt:
                turn_list.append((user_txt, assistant_txt))
            if self._should_terminate(desc, repeat, node, self._current_module_trace):
                flush_turn_list()
                stop_reason = f"goodbye_in_descendant_{desc['uid']}"
                self.trace_collector.set_stop_reason(
                    stop_reason, self._current_module_trace
                )
                self.trace_collector.set_module_turn_count(
                    self._current_module_trace, len(turn_list)
                )
                return True, stop_reason

        # 无再见触发：正常提交所有话术
        flush_turn_list()

        # 记录追踪数据
        self.trace_collector.set_module_turn_count(
            self._current_module_trace, len(turn_list)
        )
        self.trace_collector.set_module_ancestors_descendants(
            self._current_module_trace, len(ancestors), len(descendant_chain)
        )
        return False, ""

    def _apply_pressure(
        self,
        node: str,
        repeat: int,
        case: Dict[str, Any],
        messages: List[Dict],
        idx: int,  # 当前模块在路径中的索引（从0开始）
        total: int,  # 路径总模块数
    ):
        """根据动态概率决定是否附加施压话术（带全局次数限制）"""
        if node not in self.insert_nodes:
            return
        if self.pressure_count >= self.pressure_max_total:
            return

        # 计算动态概率
        if self.pressure_dynamic_enabled and total > 1:
            if self.pressure_position_mode == "normalized":
                t = idx / (total - 1)
            else:  # absolute
                t = min(1.0, idx / self.max_expected_modules)
            prob = self.pressure_start_prob + (self.pressure_end_prob - self.pressure_start_prob) * (t ** self.pressure_curve_exponent)
            weight = self.module_pressure_weights.get(node, 1.0)
            prob = min(1.0, prob * weight)
        else:
            prob = self.pressure_prob

        if self.rng.random() > prob:  # 不施压
            return

        pressure_segment, has_customer_first = (
            self.pressure_manager.get_pressure_segment(
                repeat, case, self.condition_evaluator, module_name=node
            )
        )
        if not pressure_segment:
            return

        should_merge = (not has_customer_first) and (len(messages) > 0)
        if should_merge:
            self._append_segment(messages, pressure_segment, merge_last=True)
        else:
            self._append_segment(messages, pressure_segment, merge_last=False)

        self.trace_collector.set_module_pressure(
            self._current_module_trace,
            applied=True,
            seg_len=len(pressure_segment),
            merge_last=should_merge,
        )
        self.pressure_count += 1

    def build(
        self, path: List[str], case: Dict[str, Any], prompt_text: str
    ) -> List[Dict]:
        """生成一条完整的对话消息列表"""
        self.trace_collector.start_dialogue(path, case.get("客户姓名", "unknown"))
        # 重置施压次数计数
        self.pressure_count = 0

        messages = []
        sys_content = f"你是一个{case.get('抬头', '催收专员')}，请根据客户的情况，使用合适的话术与客户进行沟通，争取让客户承诺还款。\n{prompt_text}"
        messages.append({"role": "system", "content": sys_content})

        node_counts = {}
        overall_stop_reason = None
        total_modules = len(path)

        for idx, node in enumerate(path):
            repeat = node_counts.get(node, 0) + 1
            node_counts[node] = repeat

            self._current_module_trace = self.trace_collector.start_module(node, repeat)

            stop_dialogue, stop_reason = self._process_module(
                node, repeat, case, messages, node_counts
            )
            if stop_dialogue:
                overall_stop_reason = stop_reason
                break

            # 施压话术（在正常提交后附加）
            self._apply_pressure(node, repeat, case, messages, idx, total_modules)

        else:
            if overall_stop_reason is None:
                self.trace_collector.set_stop_reason("path_natural_end")

        # 占位符填充
        for msg in messages:
            if "content" in msg:
                msg["content"] = fill_placeholders(msg["content"], case)

        return messages

    def get_trace_data(self) -> Dict:
        """返回当前对话的追踪数据（仅在 trace_enabled 时有效）"""
        return self.trace_collector.to_dict()
