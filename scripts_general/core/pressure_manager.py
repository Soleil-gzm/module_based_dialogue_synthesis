import pandas as pd
import logging
from typing import List, Dict, Any, Tuple
from core.random_service import RandomService
from core.utterance import get_ancestors, get_random_descendant_chain, sample_utterance

logger = logging.getLogger("DialogueBuilder")

class PressureManager:
    """管理施压话术模块，支持 repeat、继承、条件、随机后代链"""
    def __init__(self, pressure_df: pd.DataFrame, rng: RandomService):
        self.df = pressure_df
        self.rng = rng
        # 预计算可用的 repeat 值及最大 repeat
        self._available_repeats = set()
        for val in self.df['repeat(次数)'].dropna():
            for r in str(val).split('/'):
                if r.strip().isdigit():
                    self._available_repeats.add(int(r.strip()))
        self.max_repeat = max(self._available_repeats) if self._available_repeats else 3

    def get_pressure_segment(self, repeat: int, case: Dict[str, Any], condition_evaluator, module_name: str = None) -> Tuple[List[Dict[str, str]], bool]:
        """
        根据 repeat 次数从施压话术表中抽取一个话术片段（可能包含多轮）。
        返回 (segment_list, has_customer_first), 其中 segment_list 每个元素为 {"user": str, "assistant": str}
        has_customer_first 表示片段第一轮是否有客户话术（用于外部拼接逻辑）。
        """
        if self.df.empty:
            return [], False

        # 超出范围时降级使用最大 repeat
        effective_repeat = repeat if repeat <= self.max_repeat else self.max_repeat
        # if effective_repeat != repeat:
        #     logger.warning(f"施压话术表最大 repeat={self.max_repeat}，请求 repeat={repeat}，降级使用 repeat={effective_repeat}")
        if effective_repeat != repeat:
            if module_name:
                logger.warning(f"模块 '{module_name}' 请求 repeat={repeat}，施压话术表最大 repeat={self.max_repeat}，降级使用 repeat={effective_repeat}")
            else:
                logger.warning(f"施压话术表最大 repeat={self.max_repeat}，请求 repeat={repeat}，降级使用 repeat={effective_repeat}")
        

        # 筛选 repeat 匹配的行
        mask = self.df['repeat(次数)'].apply(
            lambda x: str(effective_repeat) in str(x).split('/') if pd.notna(x) else False)
        candidates = self.df[mask]
        if candidates.empty:
            return [], False

        # 条件筛选
        valid_rows = []
        for _, row in candidates.iterrows():
            cond_str = row.get('conditions(条件)', '')
            if condition_evaluator.evaluate(cond_str, case):        # 调用条件解析，判断抽取话术是否适用于该案例
                valid_rows.append(row)
        if not valid_rows:
            return [], False

        row = self.rng.choice(valid_rows)

        # 获取祖先和后代链
        ancestors = get_ancestors(row['uid'], self.df)
        descendant_chain = get_random_descendant_chain(row['uid'], self.df, self.rng)

        # 构建片段轮次列表
        segment = []
        for anc in ancestors:
            user = sample_utterance(anc, True, self.rng)
            assistant = sample_utterance(anc, False, self.rng)
            if user or assistant:
                segment.append({"user": user, "assistant": assistant})
        # 当前行
        user_cur = sample_utterance(row, True, self.rng)
        assistant_cur = sample_utterance(row, False, self.rng)
        segment.append({"user": user_cur, "assistant": assistant_cur})
        for desc in descendant_chain:
            user = sample_utterance(desc, True, self.rng)
            assistant = sample_utterance(desc, False, self.rng)
            if user or assistant:
                segment.append({"user": user, "assistant": assistant})

        # 判断第一轮是否有客户话术
        has_customer_first = bool(segment[0].get("user")) if segment else False
        return segment, has_customer_first