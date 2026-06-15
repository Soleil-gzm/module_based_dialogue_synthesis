import logging
from typing import Any, Dict, List, Tuple

import pandas as pd
from core.config import Config
from core.random_service import RandomService
from core.utterance import get_ancestors, get_random_descendant_chain, sample_utterance
from core.trace import TraceCollector

logger = logging.getLogger("DialogueBuilder")


class PressureManager:
    """管理施压话术模块，支持 repeat、继承、条件、随机后代链"""

    def __init__(self, pressure_df: pd.DataFrame, rng: RandomService, config: Config):
        self.df = pressure_df
        self.rng = rng
        # 预计算可用的 repeat 值及最大 repeat
        self._available_repeats = set()
        for val in self.df["repeat(次数)"].dropna():
            for r in str(val).split("/"):
                if r.strip().isdigit():
                    self._available_repeats.add(int(r.strip()))
        self.max_repeat = max(self._available_repeats) if self._available_repeats else 3
        self.flexible_stop_prob = config.get("flexible_stop_prob", 0.3)

    def get_pressure_segment(
        self,
        repeat: int,
        case: Dict[str, Any],
        condition_evaluator,
        module_name: str = None,
    ) -> Tuple[List[Dict[str, str]], bool]:
        """
        根据 repeat 次数从施压话术表中抽取一个话术片段（可能包含多轮）。
        返回 (segment_list, has_customer_first), 其中 segment_list 每个元素为 {"user": str, "assistant": str}
        has_customer_first 表示片段第一轮是否有客户话术（用于外部拼接逻辑）。

        注意：如果请求的 repeat 超过施压话术表支持的最大次数，直接返回空片段，不降级。
        """
        if self.df.empty:
            return [], False

        # 如果请求的 repeat 超过施压话术表最大支持次数，直接返回空（不降级）
        if repeat > self.max_repeat:
            if module_name:
                logger.debug(
                    f"模块 '{module_name}' 请求 repeat={repeat} 超过话术表最大 repeat={self.max_repeat}，跳过施压"
                )
            return [], False

        # 筛选 repeat 匹配的行（注意：这里直接使用 repeat，不再降级）
        mask = self.df["repeat(次数)"].apply(
            lambda x: (str(repeat) in str(x).split("/") if pd.notna(x) else False)
        )
        candidates = self.df[mask]
        if candidates.empty:
            return [], False

        # 条件筛选
        valid_rows = []
        for _, row in candidates.iterrows():
            cond_str = row.get("conditions(条件)", "")
            if condition_evaluator.evaluate(cond_str, case):
                valid_rows.append(row)
        if not valid_rows:
            return [], False

        row = self.rng.choice(valid_rows)

        # 获取祖先和后代链
        ancestors = get_ancestors(row["uid"], self.df)
        descendant_chain, flexible_stopped = get_random_descendant_chain(
            row["uid"], self.df, self.rng, flexible_stop_prob=self.flexible_stop_prob
        )

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
        return segment, has_customer_first, flexible_stopped
