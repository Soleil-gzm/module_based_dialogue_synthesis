import logging
import random
from typing import Any, Dict, List, Tuple

import pandas as pd
from core.utils.random_service import RandomService

logger = logging.getLogger("DialogueBuilder")


# ============================================================
# 条件解析的安全包装
# ============================================================
def _safe_evaluate(condition_evaluator, cond_str, case) -> bool:
    """
    条件解析的安全包装：
    - condition_evaluator 或 case 为 None → 不做过滤，返回 True
    - 解析异常 → 记录 warning，返回 False（不满足条件）
    - 正常 → 返回 bool(evaluate(...))
    """
    if condition_evaluator is None or case is None:
        return True
    try:
        return bool(condition_evaluator.evaluate(cond_str, case))
    except Exception as e:
        logger.warning(f"条件解析失败: {cond_str!r} -> {e}")
        return False


# ============================================================
# 话术抽样
# ============================================================
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


# ============================================================
# 祖先链
# ============================================================
def get_ancestors(
    uid: int,
    df: pd.DataFrame,
    rng: RandomService,
    condition_evaluator=None,
    case=None,
    max_depth: int = 20,
) -> List[pd.Series]:
    """
    递归获取所有祖先行（从远祖到父的顺序）。

    规则：
    - 如果 parent(继承) 包含多个值（用 / 分隔），先按条件过滤候选父级，
      再从满足条件的候选中随机选择一个作为父级；全部不满足则中断继承。
    - 若提供 condition_evaluator 和 case，则只返回满足条件的祖先行。
    - 通过 visited 防止 parent 成环导致死循环。
    - 通过 max_depth 防止超长链导致性能问题。
    """
    ancestors: List[pd.Series] = []
    visited = set()
    depth = 0

    current_uid = uid
    while True:
        # ---- 防环 & 深度上限 ----
        if current_uid in visited:
            logger.warning(f"get_ancestors: 检测到 parent 环，中断于 uid={current_uid}")
            break
        if depth >= max_depth:
            logger.warning(
                f"get_ancestors: 祖先链深度超过上限 {max_depth}，中断于 uid={current_uid}"
            )
            break
        visited.add(current_uid)
        depth += 1

        # ---- 取当前行的 parent 值 ----
        parent_col = df.loc[df["uid"] == current_uid, "parent(继承)"]
        if parent_col.empty:
            break
        parent_val = parent_col.values[0]
        if pd.isna(parent_val) or parent_val == 0:
            break

        # ---- 解析候选父级 uid 列表 ----
        if isinstance(parent_val, str) and "/" in parent_val:
            candidate_uids = [
                int(p.strip()) for p in parent_val.split("/") if p.strip().isdigit()
            ]
        else:
            try:
                candidate_uids = [int(parent_val)]
            except (ValueError, TypeError):
                break
        if not candidate_uids:
            break

        # ---- 条件解析：候选父级先过滤，再随机选 ----
        candidates: List[Tuple[int, pd.Series]] = []
        for candidate_uid in candidate_uids:
            parent_rows = df[df["uid"] == candidate_uid]
            if parent_rows.empty:
                continue
            candidate_series = parent_rows.iloc[0]
            cond_str = candidate_series.get("conditions(条件)", "")
            if not _safe_evaluate(condition_evaluator, cond_str, case):
                continue
            candidates.append((candidate_uid, candidate_series))

        # 所有候选父级都不满足条件 → 中断
        if not candidates:
            break

        # ---- 从满足条件的候选中选一个父级 ----
        if len(candidates) == 1:
            parent_uid, parent_series = candidates[0]
        else:
            parent_uid, parent_series = rng.choice(candidates)

        ancestors.append(parent_series)
        current_uid = parent_uid

    return list(reversed(ancestors))


# ============================================================
# 后代链
# ============================================================
def get_random_descendant_chain(
    uid: int,
    df: pd.DataFrame,
    rng: RandomService,
    flexible_stop_prob: float = 0.3,
    max_depth: int = 10,
    condition_evaluator=None,
    case=None,
) -> Tuple[List[pd.Series], bool]:
    """
    获取从当前行（uid）开始的一条随机后代链。
    返回 (chain, stopped_by_flexible)，chain 不包含起始行本身。
    """
    current_rows = df[df["uid"] == uid]
    if current_rows.empty:
        return [], False
    current_row = current_rows.iloc[0]

    if should_stop_by_flexible(current_row, rng, flexible_stop_prob):
        return [], True

    def contains_parent(row):
        parent_val = row.get("parent(继承)")
        if pd.isna(parent_val):
            return False
        parts = str(parent_val).split("/")
        return str(uid) in [p.strip() for p in parts]

    children = df[df.apply(contains_parent, axis=1)]

    # 条件过滤子节点（使用安全包装）
    if condition_evaluator is not None and case is not None:
        children = children[
            children.apply(
                lambda row: _safe_evaluate(
                    condition_evaluator, row.get("conditions(条件)", ""), case
                ),
                axis=1,
            )
        ]

    if children.empty or max_depth <= 0:
        return [], False

    child_row = children.sample(n=1, random_state=rng.randint(0, 2**32 - 1)).iloc[0]
    chain = [child_row]

    if should_stop_by_flexible(child_row, rng, flexible_stop_prob):
        return chain, True

    deeper, deeper_stop = get_random_descendant_chain(
        child_row["uid"],
        df,
        rng,
        flexible_stop_prob,
        max_depth - 1,
        condition_evaluator,
        case,
    )
    chain.extend(deeper)
    return chain, deeper_stop


# ============================================================
# 占位符填充
# ============================================================
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
        "{逾期天数}": case.get("逾期天数_显示", ""),
        "{今天日期}": case.get("今天日期", ""),
        "{查账时间}": case.get("查账时间", ""),
        "{当前时间}": case.get("当前时间", ""),
        "{应还金额}": case.get("应还金额", ""),
        "{总欠款}": case.get("总欠款", ""),
        "{本金}": case.get("本金", ""),
        "{利息}": case.get("利息", ""),
        "{违约金}": case.get("违约金", ""),
        "{罚息}": case.get("罚息", ""),
        "{还款日}": case.get("还款日", ""),
        "{随机金额}": case.get("随机金额", ""),
        "{随机时间}": case.get("随机时间", ""),
        "{随机数字}": case.get("随机数字", ""),
        "{随机还款日}": case.get("随机还款日", ""),
        "{总本金}": case.get("总本金", ""),
        "{逾期笔数}": case.get("逾期笔数_数值", ""),
        "{empty_tag}": "。",
    }
    for k, v in replacements.items():
        text = text.replace(k, str(v))
    return text
