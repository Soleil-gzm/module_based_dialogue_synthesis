'''
Step 6：拆分话术采样与继承链处理
操作：创建 core/utterance.py，包含：

sample_utterance(row, is_human)：从行中随机选话术

get_ancestors(uid, df)

get_random_descendant_chain(uid, df, stop_prob, max_depth)

fill_placeholders(text, case)
原因：这些函数是纯工具函数，无副作用，独立后易于单元测试，且可在不同生成器中复用。
'''

import random
import pandas as pd
from typing import List, Dict, Any
from core.random_service import RandomService

def sample_utterance(row: pd.Series, is_human: bool, rng: RandomService) -> str:
    """从一行中随机抽取一个话术（用 / 分割），使用注入的随机服务"""
    col = 'human(客户)' if is_human else 'assistant(专员)'
    text = row[col]
    if pd.isna(text):
        return ''
    options = [s.strip() for s in str(text).split('/') if s.strip()]
    if not options:
        return ''
    return rng.choice(options)

def get_ancestors(uid: int, df: pd.DataFrame) -> List[pd.Series]:
    """递归获取所有祖先行（从远祖到父的顺序）"""
    ancestors = []
    while True:
        parent_series = df.loc[df['uid'] == uid, 'parent(继承)']
        if parent_series.empty:
            break
        parent_val = parent_series.values[0]
        if pd.isna(parent_val) or parent_val == 0:
            break
        parent_row = df[df['uid'] == parent_val]
        if parent_row.empty:
            break
        ancestors.append(parent_row.iloc[0])
        uid = parent_val
    return list(reversed(ancestors))

def get_random_descendant_chain(uid: int, df: pd.DataFrame, rng: RandomService,stop_prob: float = 0.3, max_depth: int = 10) -> List[pd.Series]:
    """递归获取一条随机的后代链，使用注入的随机服务"""
    children = df[df['parent(继承)'] == uid]
    if children.empty or max_depth <= 0:
        return []
    child_row = children.sample(n=1, random_state=rng.randint(0, 2**32-1)).iloc[0]  # pandas sample 支持 random_state
    chain = [child_row]
    flex_stop = child_row.get('flexible_stop(可选不继承)', 0)
    if pd.notna(flex_stop) and flex_stop == 1 and rng.random() < stop_prob:
        return chain
    deeper = get_random_descendant_chain(child_row['uid'], df, rng, stop_prob, max_depth-1)
    chain.extend(deeper)
    return chain

def fill_placeholders(text: str, case: Dict[str, Any]) -> str:
    """替换文本中的花括号占位符"""
    if not isinstance(text, str):
        return text
    replacements = {
        '{客服电话}': case.get('客服电话', ''),
        '{机构名称}': case.get('机构名称', ''),
        '{业务类型}': case.get('业务类型', ''),
        '{APP名称}': case.get('APP名称', ''),
        '{抬头}': case.get('抬头', ''),
        '{专员工号}': case.get('专员工号', ''),
        '{客户姓名}': case.get('客户姓名', ''),
        '{客户性别}': case.get('客户性别', ''),
        '{逾期天数}': str(case.get('逾期天数', '')),
        '{今天日期}': case.get('今天日期', ''),
        '{查账时间}': case.get('查账时间', ''),
        '{逾期金额}': case.get('逾期金额', ''),
        '{总欠款}': case.get('总欠款', ''),
        '{本金}': case.get('本金', ''),
        '{还款日}': case.get('还款日', ''),
        '{随机金额}': case.get('随机金额', ''),
        '{随机时间}': case.get('随机时间', ''),
        '{随机数字}': case.get('随机数字', ''),
        '{empty_tag}': ''
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text
