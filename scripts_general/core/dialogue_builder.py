import logging
import pandas as pd
from typing import List, Dict, Any
from core.config import Config
from core.condition import ConditionEvaluator
from core.utterance import sample_utterance, get_ancestors, get_random_descendant_chain, fill_placeholders
from core.pressure_manager import PressureManager
from core.random_service import RandomService

class DialogueBuilder:
    """根据模块路径生成完整对话"""
    def __init__(self, config: Config, df_dict: Dict[str, pd.DataFrame],
                 condition_evaluator: ConditionEvaluator,
                 rng: RandomService,
                 pressure_manager: PressureManager,   # 新增参数
                 logger: logging.Logger = None):
        self.config = config
        self.df_dict = df_dict
        self.condition_evaluator = condition_evaluator
        self.rng = rng
        self.pressure_manager = pressure_manager   # 使用外部传入的实例
        self.logger = logger or logging.getLogger('DialogueBuilder')
        self.insert_nodes = set(config.get('insert_nodes', []))
        self.pressure_prob = config.get('pressure_prob', 0.6)
        self.max_repeat = config.get('max_repeat', {})
        self.goodbye_termination_prob = config.get('goodbye_termination_prob', 0.7)   # 新增

    def _should_terminate(self, row: pd.Series, repeat: int, node: str) -> bool:
        """检查是否因再见标志而终止（包含概率控制）"""
        if row.get('是否再见') == 1 and repeat <= self.max_repeat.get(node, 999):
            if self.rng.random() <= self.goodbye_termination_prob:
                self.logger.debug(f"模块 {node} repeat={repeat} 再见触发，终止对话")
                return True
            else:
                self.logger.debug(f"模块 {node} repeat={repeat} 再见被忽略（概率不触发），继续对话")
        return False

    def build(self, path: List[str], case: Dict[str, Any], prompt_text: str) -> List[Dict]:
        """生成一条完整的对话消息列表"""
        messages = []
        sys_content = f"你是一个{case.get('抬头', '催收专员')}，请根据客户的情况，使用合适的话术与客户进行沟通，争取让客户承诺还款。\n{prompt_text}"
        messages.append({"role": "system", "content": sys_content})

        node_counts = {}

        for node in path:
            node_counts[node] = node_counts.get(node, 0) + 1        # 模块出现次数
            repeat = node_counts[node]                  # repeat次进入模块根据repeat行来抽取话术
            df_node = self.df_dict.get(node)
            if df_node is None or df_node.empty:
                self.logger.debug(f"模块 {node} 无数据，跳过")
                continue

            # 筛选 repeat 匹配的行
            mask = df_node['repeat(次数)'].apply(
                lambda x: str(repeat) in str(x).split('/') if pd.notna(x) else False)
            candidates = df_node[mask]
            if candidates.empty:
                self.logger.debug(f"模块 {node} repeat={repeat} 无候选行")
                continue

            # 根据条件筛选
            valid_rows = []
            for _, row in candidates.iterrows():
                cond_str = row.get('conditions(条件)', '')
                if self.condition_evaluator.evaluate(cond_str, case):
                    valid_rows.append(row)
            if not valid_rows:
                self.logger.debug(f"模块 {node} repeat={repeat} 无满足条件的行")
                continue

            row = self.rng.choice(valid_rows)

            # 获取祖先、后代链
            ancestors = get_ancestors(row['uid'], df_node)  # 无随机，直接使用
            descendant_chain = get_random_descendant_chain(row['uid'], df_node, self.rng)

            # 构建 turn_list，同时检查再见
            turn_list = []
            stop_dialogue = False

            # 处理祖先链（一般不会有再见，但为了健壮也检查）
            for anc in ancestors:
                user_txt = sample_utterance(anc, True, self.rng)
                assistant_txt = sample_utterance(anc, False, self.rng)
                if user_txt or assistant_txt:
                    turn_list.append((user_txt, assistant_txt))
                if self._should_terminate(anc, repeat, node):
                    stop_dialogue = True
                    break       # 跳出祖先链构建
            if stop_dialogue:
                break       # 跳出全局对话构建

            # 处理当前行
            current_user = sample_utterance(row, True, self.rng)
            current_assistant = sample_utterance(row, False, self.rng)
            turn_list.append((current_user, current_assistant))
            if self._should_terminate(row, repeat, node):
                break

            # 处理后代链（可能包含再见）
            for desc in descendant_chain:
                user_txt = sample_utterance(desc, True, self.rng)
                assistant_txt = sample_utterance(desc, False, self.rng)
                if user_txt or assistant_txt:
                    turn_list.append((user_txt, assistant_txt))
                if self._should_terminate(desc, repeat, node):
                    stop_dialogue = True
                    break
            if stop_dialogue:
                break

            # 将所有 turn_list 中的话术添加到 messages
            for user_txt, assistant_txt in turn_list:
                if user_txt:
                    messages.append({"role": "user", "content": user_txt})
                if assistant_txt:
                    messages.append({"role": "assistant", "content": assistant_txt, "loss": "True"})

            # ========== 施压话术处理开始 ==========
            if node in self.insert_nodes and self.rng.random() <= self.pressure_prob:
                pressure_segment, has_customer_first = self.pressure_manager.get_pressure_segment(
                    repeat, case, self.condition_evaluator, module_name=node
                )
                if pressure_segment:
                    if not has_customer_first and messages:
                        last_msg = messages[-1]
                        if last_msg["role"] == "assistant":
                            # 合并第一条施压专员话术到上一轮
                            last_msg["content"] += pressure_segment[0]["assistant"]
                            # 剩余部分（如果有）作为新轮次追加
                            for seg in pressure_segment[1:]:
                                if seg.get("user"):
                                    messages.append({"role": "user", "content": seg["user"]})
                                if seg.get("assistant"):
                                    messages.append({"role": "assistant", "content": seg["assistant"], "loss": "True"})
                        else:
                            # 上一轮不是 assistant，则全部作为新轮次
                            for seg in pressure_segment:
                                if seg.get("user"):
                                    messages.append({"role": "user", "content": seg["user"]})
                                if seg.get("assistant"):
                                    messages.append({"role": "assistant", "content": seg["assistant"], "loss": "True"})
                    else:
                        # 第一轮有客户话术：整个片段作为新轮次追加
                        for seg in pressure_segment:
                            if seg.get("user"):
                                messages.append({"role": "user", "content": seg["user"]})
                            if seg.get("assistant"):
                                messages.append({"role": "assistant", "content": seg["assistant"], "loss": "True"})
            # ========== 施压话术处理结束 ==========

        # 占位符填充（无随机）
        for msg in messages:
            if 'content' in msg:
                msg['content'] = fill_placeholders(msg['content'], case)
        return messages