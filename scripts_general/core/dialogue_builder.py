import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from core.condition import ConditionParser
from core.config import Config
from core.factory import create_pressure_strategy,create_probability_calculator
from core.pressure_manager import PressureManager
from core.random_service import RandomService
from core.trace import TraceCollector
from core.utterance import (
    fill_placeholders,
    get_ancestors,
    get_random_descendant_chain,
    sample_utterance,
)


class DialogueBuilder:
    """根据模块路径生成完整对话"""

    def __init__(
        self,
        config: Config,
        df_dict: Dict[str, pd.DataFrame],
        rng: RandomService,
        pressure_manager: PressureManager,
        logger: logging.Logger = None,
    ):
        self.config = config
        self.df_dict = df_dict
        self.condition_evaluator = ConditionParser()
        self.rng = rng
        self.pressure_manager = pressure_manager
        self.logger = logger or logging.getLogger("DialogueBuilder")
        self.insert_nodes = set(config.get("insert_nodes", []))
        self.pressure_prob = config.get("pressure_prob", 0.6)  # 保留兼容旧配置
        self.max_repeat = config.get("max_repeat", {})
        self.trace_enabled = config.get("trace_enabled", False)
        self.trace_collector = TraceCollector(self.trace_enabled)

        # 动态施压话术配置
        self.pressure_dynamic_enabled = config.get("pressure_dynamic_enabled", True)
        self.pressure_max_total = config.get("pressure_max_total", 3)
        self.module_pressure_weights = config.get("module_pressure_weights", {})
        self.pressure_strategy = create_pressure_strategy(config)
        # 施压概率计算器
        self.pressure_prob_calc = create_probability_calculator(config, "pressure")

        # 动态再见概率配置
        self.goodbye_dynamic_enabled = config.get("goodbye_dynamic_enabled", False)
        if self.goodbye_dynamic_enabled:
            self.goodbye_prob_calc = create_probability_calculator(config, "goodbye")
        else:
            self.goodbye_prob_calc = None
        self.goodbye_min_idx = config.get("goodbye_min_idx", 0)      # 强制忽略前 N 个模块
        self.goodbye_fixed_prob = config.get("goodbye_termination_prob", 0.7)  # 固定概率

        # 辅助变量（每次 build 时重置）
        self.pressure_count = 0

    def _should_terminate(
        self,
        row: pd.Series,
        repeat: int,
        node: str,
        module_trace: Dict = None,
        idx: int = 0,
        total: int = 0,
    ) -> bool:
        """检查是否因再见标志而终止（包含概率控制），并记录 trace"""
        if row.get("是否再见") != 1 or repeat > self.max_repeat.get(node, 999):
            return False

        # 计算再见概率
        if self.goodbye_dynamic_enabled and total > 1:
            # 强制忽略前 N 个模块（索引 < goodbye_min_idx）
            if idx < self.goodbye_min_idx:
                prob = 0.0
            else:
                t = idx / (total - 1)
                prob = self.goodbye_prob_calc.calculate(t)
        else:
            prob = self.goodbye_fixed_prob

        if self.rng.random() <= prob:
            self.logger.debug(f"模块 {node} repeat={repeat} 再见触发，终止对话")
            if module_trace:
                self.trace_collector.set_module_goodbye(module_trace, triggered=True)
            return True
        else:
            self.logger.debug(
                f"模块 {node} repeat={repeat} 再见被忽略（概率不触发），继续对话"
            )
            if module_trace:
                self.trace_collector.set_module_goodbye(module_trace, triggered=False)
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
        module_idx: int,          # 新增：当前模块在路径中的索引
        total_modules: int,       # 新增：路径总模块数
    ) -> Tuple[bool, str]:
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
            eval_result = self.condition_evaluator.evaluate_with_metadata(cond_str, case)
            if eval_result["matched"]:
                row_with_meta = row.copy()
                row_with_meta["_condition_meta"] = eval_result
                valid_rows.append(row_with_meta)
        if not valid_rows:
            self.logger.debug(f"模块 {node} repeat={repeat} 无满足条件的行")
            self.trace_collector.set_module_status(
                self._current_module_trace, "skipped_condition_mismatch"
            )
            return False, ""

        row = self.rng.choice(valid_rows)
        condition_meta = row.get("_condition_meta", {})
        self._current_condition_meta = condition_meta
        self.trace_collector.set_module_selected_uid(
            self._current_module_trace, row["uid"]
        )
        # 新增：把 Excel 里的原始条件字符串也记入 trace
        self._current_module_trace["condition_text"] = row.get("conditions(条件)", "")

        # 提取 flexible_stop 和是否再见的原始值
        flexible_val = row.get("flexible_stop(可选不继承)", 0)
        goodbye_val = row.get("是否再见", 0)

        try:
            flexible_val = int(flexible_val) if flexible_val is not None else 0
        except (ValueError, TypeError):
            flexible_val = 0
        try:
            goodbye_val = int(goodbye_val) if goodbye_val is not None else 0
        except (ValueError, TypeError):
            goodbye_val = 0

        self.trace_collector.set_module_flexible_value(
            self._current_module_trace, flexible_val
        )
        self.trace_collector.set_module_goodbye_value(
            self._current_module_trace, goodbye_val
        )

        # 获得前后继承链（传递条件评估器以过滤不满足条件的行）
        ancestors = get_ancestors(
            row["uid"], df_node, self.rng,
            condition_evaluator=self.condition_evaluator,
            case=case
        )
        descendant_chain, flexible_stopped = get_random_descendant_chain(
            row["uid"],
            df_node,
            self.rng,
            flexible_stop_prob=self.config.get("flexible_stop_prob", 0.3),
            condition_evaluator=self.condition_evaluator,
            case=case
        )
        if flexible_stopped:
            self.trace_collector.set_module_flexible_stop(
                self._current_module_trace, True
            )

        turn_list = []
        stop_reason = ""

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
            if self._should_terminate(
                anc, repeat, node, self._current_module_trace, module_idx, total_modules
            ):
                flush_turn_list()
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
        if self._should_terminate(
            row, repeat, node, self._current_module_trace, module_idx, total_modules
        ):
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
            if self._should_terminate(
                desc, repeat, node, self._current_module_trace, module_idx, total_modules
            ):
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

        # 记录继承链信息
        parent_raw = row.get("parent(继承)", None)
        ancestor_uids = [anc["uid"] for anc in ancestors]
        descendant_uids = [desc["uid"] for desc in descendant_chain]

        self.trace_collector.set_module_turn_count(
            self._current_module_trace, len(turn_list)
        )
        self.trace_collector.set_module_utterance_chain(
            self._current_module_trace,
            ancestor_uids,
            descendant_uids,
            parent_raw,
        )

        return False, ""
    
    def _apply_pressure(
        self,
        node: str,
        repeat: int,
        case: Dict[str, Any],
        messages: List[Dict],
        idx: int,
        total: int,
    ):
        if node not in self.insert_nodes:
            return
        if self.pressure_count >= self.pressure_max_total:
            return

        # 计算施压概率
        if self.pressure_dynamic_enabled and total > 1:
            t = self.pressure_strategy.get_normalized_position(idx, total)
            base_prob = self.pressure_prob_calc.calculate(t)
            weight = self.module_pressure_weights.get(node, 1.0)
            prob = min(1.0, base_prob * weight)
        else:
            prob = self.pressure_prob

        # 记录跳过施压
        if self.rng.random() > prob:
            self.trace_collector.set_module_pressure(
                self._current_module_trace,
                applied=False,
                pass_=True,
                prob_used=prob,
            )
            return

        pressure_segment, has_customer_first, flexible_stopped = (
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

        # 记录施压应用信息
        self.trace_collector.set_module_pressure(
            self._current_module_trace,
            applied=True,
            pass_=False,
            prob_used=prob,
            merge_last=should_merge,
            turn_count=len(pressure_segment),
            flexible_triggered_in_pressure=flexible_stopped,
        )
        self.pressure_count += 1

    def build(
        self, path: List[str], case: Dict[str, Any], prompt_text: str
    ) -> List[Dict]:
        case_id = case.get("_filename", case.get("客户姓名", "unknown"))
        self.trace_collector.start_dialogue(path, case_id)
        self.pressure_count = 0
        self._current_condition_meta = {"requires_abs_overdue": False}

        messages = []
        sys_content = f"{prompt_text}"
        messages.append({"role": "system", "content": sys_content})

        node_counts = {}
        overall_stop_reason = None
        total_modules = len(path)

        for idx, node in enumerate(path):
            repeat = node_counts.get(node, 0) + 1
            node_counts[node] = repeat

            self._current_module_trace = self.trace_collector.start_module(node, repeat)

            stop_dialogue, stop_reason = self._process_module(
                node, repeat, case, messages, node_counts, idx, total_modules
            )
            if stop_dialogue:
                overall_stop_reason = stop_reason
                break

            # 施压话术（在正常提交后附加）
            self._apply_pressure(node, repeat, case, messages, idx, total_modules)

        else:
            if overall_stop_reason is None:
                self.trace_collector.set_stop_reason("path_natural_end")

        # 占位符填充（始终使用逾期天数_显示，已取绝对值）
        for msg in messages:
            if "content" in msg:
                msg["content"] = fill_placeholders(msg["content"], case)

        # 计算总轮数并存入 trace
        if self.trace_enabled:
            total_turns = 0
            total_pressure_turns = 0
            for mod in self.trace_collector.data.get("modules", []):
                total_turns += mod.get("turn_count", 0)
                total_pressure_turns += mod["pressure"].get("turn_count", 0)
            self.trace_collector.set_dialogue_summary(total_turns, total_pressure_turns)

        return messages

    def get_trace_data(self) -> Dict:
        """返回当前对话的追踪数据（仅在 trace_enabled 时有效）"""
        return self.trace_collector.to_dict()
