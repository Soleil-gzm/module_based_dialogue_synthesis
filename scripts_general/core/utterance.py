import random
from typing import Any, Dict, List, Tuple

import pandas as pd
from core.random_service import RandomService


def sample_utterance(row: pd.Series, is_human: bool, rng: RandomService) -> str:
    """从一行中随机抽取一个话术（用 / 分割），使用注入的随机服务"""
    col = "human(客户)" if is_human else "assistant(专员)"
    text = row[col]
    if pd.isna(text):
        return ""
    options = [s.strip() for s in str(text).split("/") if s.strip()]
    if not options:
        return ""
    return rng.choice(options)


def should_stop_by_flexible(
    row: pd.Series, rng: RandomService, stop_prob: float
) -> bool:
    """
    判断当前行是否因 flexible_stop 而应停止继续处理（后代链或当前行后续）
    :param row: 话术行（包含 flexible_stop(可选不继承) 字段）
    :param rng: 随机服务
    :param stop_prob: 停止概率（配置文件中的 flexible_stop_prob）
    :return: True 表示应停止（不再向后继承或继续），False 表示继续
    """
    flex_stop_val = row.get("flexible_stop(可选不继承)", 0)
    # 转换为整数，兼容字符串或数字
    try:
        flex_stop = int(flex_stop_val)
    except (ValueError, TypeError):
        flex_stop = 0
    # 只有当字段为1且随机数小于停止概率时才停止
    return flex_stop == 1 and rng.random() <= stop_prob


def get_ancestors(uid: int, df: pd.DataFrame, rng: RandomService) -> List[pd.Series]:
    """
    递归获取所有祖先行（从远祖到父的顺序）。
    如果 parent(继承) 包含多个值（用 / 分隔），则随机选择一个作为父级。
    """
    ancestors = []
    while True:
        parent_series = df.loc[df["uid"] == uid, "parent(继承)"]
        if parent_series.empty:
            break
        parent_val = parent_series.values[0]
        if pd.isna(parent_val) or parent_val == 0:
            break

        # 处理多值情况：如果是字符串且包含 '/'
        if isinstance(parent_val, str) and "/" in parent_val:
            # 分割并去除空格，过滤掉空字符串
            possible_parents = [
                int(p.strip()) for p in parent_val.split("/") if p.strip().isdigit()
            ]
            if not possible_parents:
                break
            # 随机选择一个父级
            parent_uid = rng.choice(possible_parents)
        else:
            try:
                parent_uid = int(parent_val)
            except (ValueError, TypeError):
                break

        parent_row = df[df["uid"] == parent_uid]
        if parent_row.empty:
            break
        ancestors.append(parent_row.iloc[0])
        uid = parent_uid
    return list(reversed(ancestors))


def get_random_descendant_chain(
    uid: int,
    df: pd.DataFrame,
    rng: RandomService,
    flexible_stop_prob: float = 0.3,
    max_depth: int = 10,
) -> Tuple[List[pd.Series], bool]:
    # 首先获取当前行（起始行）
    current_rows = df[df["uid"] == uid]
    if current_rows.empty:
        return [], False
    current_row = current_rows.iloc[0]

    if should_stop_by_flexible(current_row, rng, flexible_stop_prob):
        return [], True

    # 查找子节点：parent(继承) 字段包含当前 uid 的行
    def contains_parent(row):
        parent_val = row.get("parent(继承)")
        if pd.isna(parent_val):
            return False
        # 将 parent 值转为字符串，按 / 分割，检查是否包含 uid
        parts = str(parent_val).split("/")
        return str(uid) in [p.strip() for p in parts]

    children = df[df.apply(contains_parent, axis=1)]
    if children.empty or max_depth <= 0:
        return [], False

    child_row = children.sample(n=1, random_state=rng.randint(0, 2**32 - 1)).iloc[0]
    chain = [child_row]

    if should_stop_by_flexible(child_row, rng, flexible_stop_prob):
        return chain, True

    deeper, deeper_stop = get_random_descendant_chain(
        child_row["uid"], df, rng, flexible_stop_prob, max_depth - 1
    )
    chain.extend(deeper)
    return chain, deeper_stop


def fill_placeholders(text: str, case: Dict[str, Any]) -> str:
    """替换文本中的花括号占位符"""
    if not isinstance(text, str):
        return text
    replacements = {
        "{客服电话}": case.get("客服电话", ""),
        "{机构名称}": case.get("机构名称", ""),
        "{业务类型}": case.get("业务类型", ""),
        "{APP名称}": case.get("APP名称", ""),
        "{抬头}": case.get("抬头", ""),
        "{专员工号}": case.get("专员工号", ""),
        "{客户姓名}": case.get("客户姓名", ""),
        "{客户性别}": case.get("客户性别", ""),
        "{客户姓氏}": case.get("客户姓氏", ""),
        "{逾期天数}": str(case.get("逾期天数", "")),
        "{今天日期}": case.get("今天日期", ""),
        "{查账时间}": case.get("查账时间", ""),
        "{当前时间}": case.get("当前时间", ""),
        "{逾期金额}": case.get("逾期金额", ""),
        "{总欠款}": case.get("总欠款", ""),
        "{本金}": case.get("本金", ""),
        "{利息}": case.get("利息", ""),
        "{违约金}": case.get("违约金", ""),
        "{罚息}": case.get("罚息", ""),
        "{还款日}": case.get("还款日", ""),
        "{随机金额}": case.get("随机金额", ""),
        "{随机时间}": case.get("随机时间", ""),
        "{随机数字}": case.get("随机数字", ""),
        "{empty_tag}": "",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text
