'''
Step 7：拆分对话构建器
操作：创建 core/dialogue_builder.py，类 DialogueBuilder：

初始化接收 config, df_dict, condition_evaluator

方法 build_dialogue(path, case, prompt) 返回 messages 列表

内部整合继承链、施压话术、占位符填充等逻辑。
原因：对话生成是核心流程，将其与路径生成、数据加载解耦，便于单独调整对话风格（如施压策略、轮次顺序）。
'''

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
                 logger: logging.Logger = None):
        self.config = config
        self.df_dict = df_dict
        self.condition_evaluator = condition_evaluator
        self.rng = rng
        self.logger = logger or logging.getLogger('DialogueBuilder')
        self.insert_nodes = set(config.get('insert_nodes', []))
        self.pressure_prob = config.get('pressure_prob', 0.6)
        self.max_repeat = config.get('max_repeat', {})
        pressure_df = df_dict.get('衔接施压话术', pd.DataFrame())
        self.pressure_manager = PressureManager(pressure_df, rng)

    def build(self, path: List[str], case: Dict[str, Any], prompt_text: str) -> List[Dict]:
        """生成一条完整的对话消息列表"""
        messages = []
        sys_content = f"你是一个{case.get('抬头', '催收专员')}，请根据客户的情况，使用合适的话术与客户进行沟通，争取让客户承诺还款。\n{prompt_text}"
        messages.append({"role": "system", "content": sys_content})

        node_counts = {}
        self.pressure_manager.reset()

        for node in path:
            node_counts[node] = node_counts.get(node, 0) + 1
            repeat = node_counts[node]
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

            # 构建 turn_list
            turn_list = []
            for anc in ancestors:
                user_txt = sample_utterance(anc, True, self.rng)
                assistant_txt = sample_utterance(anc, False, self.rng)
                if user_txt or assistant_txt:
                    turn_list.append((user_txt, assistant_txt))

            current_user = sample_utterance(row, True, self.rng)
            current_assistant = sample_utterance(row, False, self.rng)

            # 附加施压话术（仅当无祖先且无后代时）
            if node in self.insert_nodes and len(ancestors) == 0 and len(descendant_chain) == 0:
                if self.rng.random() < self.pressure_prob:
                    pressure_text = self.pressure_manager.get_next_pressure()
                    current_assistant += pressure_text

            turn_list.append((current_user, current_assistant))

            for desc in descendant_chain:
                user_txt = sample_utterance(desc, True, self.rng)
                assistant_txt = sample_utterance(desc, False, self.rng)
                if user_txt or assistant_txt:
                    turn_list.append((user_txt, assistant_txt))

            # 添加到 messages
            for user_txt, assistant_txt in turn_list:
                if user_txt:
                    messages.append({"role": "user", "content": user_txt})
                if assistant_txt:
                    messages.append({"role": "assistant", "content": assistant_txt,"loss:":"True"})

            # 检查是否再见（如果 row 有 '是否再见' == 1 且未达最大重复次数）
            if row.get('是否再见') == 1 and repeat < self.max_repeat.get(node, 999):
                self.logger.debug(f"模块 {node} repeat={repeat} 遇到再见标识，提前终止")
                break

        # 占位符填充（无随机）
        for msg in messages:
            if 'content' in msg:
                msg['content'] = fill_placeholders(msg['content'], case)
        return messages