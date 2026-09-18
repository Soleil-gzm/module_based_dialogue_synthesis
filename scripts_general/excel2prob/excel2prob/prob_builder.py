"""
生成 prob 概率表模块

公开接口：
    build_prob_matrix(payload, yaml_path, compress_mode) -> pd.DataFrame
    save_prob_matrix(matrix, output_path) -> str
    validate_matrix(matrix) -> List[str]

优先级（从高到低）：
    1. fixed_prob：固定值精确使用，剩余按行数比例分配，不参与压缩/boost
    2. manual weights：精确覆盖，走归一化
    3. 自动计算：压缩 + boost + self_loop，归一化

业务偏好配置（全部可选，不写则行为不变）：
    boost:
        模块名: 倍数

    self_loop_boost: 1.5
    或
    self_loop_boost:
        A: 1.5
        B: 3.0
        C: 1.0
        default: 0.9

    self_loop_boost_override:
        模块名: 倍数

    fixed_prob:
        行模块名:
            候选模块名: 固定百分比
            ...

归一化：
    使用最大余数法，保证每行概率和精确为 100.00
"""

import math
import os
from typing import Dict, List, Set

import pandas as pd
import yaml


# ============================================================
# 1. 读取 YAML
# ============================================================
def load_yaml_categories(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ============================================================
# 2. 模块顺序：manual → A → B → C
# ============================================================
def get_module_order(config: dict, candidates: Dict) -> List[str]:
    order = []
    for m in (config.get("manual", {}) or {}).keys():
        if m in candidates and m not in order:
            order.append(m)
    for cat in ("A", "B", "C"):
        for m in config.get(cat, []) or []:
            if m in candidates and m not in order:
                order.append(m)
    for m in candidates:
        if m not in order:
            order.append(m)
    return order


# ============================================================
# 3. 展平候选
# ============================================================
def flatten_candidates(cand) -> List[str]:
    if isinstance(cand, list):
        return cand
    if "weights" in cand:
        return list(cand["weights"].keys())
    result, seen = [], set()
    for cat in ("A", "B", "C"):
        for m in cand.get(cat, []):
            if m not in seen:
                seen.add(m)
                result.append(m)
    return result


# ============================================================
# 4. 压缩函数
# ============================================================
def compress(value: float, mode: str = "sqrt") -> float:
    if value <= 0:
        return 0.0
    if mode == "none":
        return value
    if mode == "sqrt":
        return math.sqrt(value)
    if mode == "log":
        return math.log(value + 1)
    raise ValueError(f"未知压缩方式: {mode}")


# ============================================================
# 5. 归一化：最大余数法，保证和 = 100.00
# ============================================================
def normalize_to_100(weights: Dict[str, float]) -> Dict[str, float]:
    """
    把权重归一化到和为 100 的百分数，使用最大余数法保证精确。
    """
    total = sum(weights.values())
    if total <= 0:
        return {m: 0.0 for m in weights}

    exact = {m: w / total * 100 for m, w in weights.items()}
    floored = {m: math.floor(v * 100) / 100 for m, v in exact.items()}
    diff = round(100 - sum(floored.values()), 2)

    if diff <= 0:
        return floored

    remainders = sorted(
        exact.keys(),
        key=lambda m: exact[m] - floored[m],
        reverse=True,
    )

    n = len(remainders)
    idx = 0
    while diff >= 0.01 - 1e-9:
        m = remainders[idx % n]
        floored[m] = round(floored[m] + 0.01, 2)
        diff = round(diff - 0.01, 2)
        idx += 1
        if idx > n * 2:
            break

    return floored


# ============================================================
# 6. 自循环倍数解析（支持数字 / 字典两种形式）
# ============================================================
def get_self_loop_multiplier(
    target: str,
    a_set: Set[str],
    b_set: Set[str],
    c_set: Set[str],
    self_loop_boost,
) -> float:
    """
    self_loop_boost 支持两种形式：
      - 数字：所有模块统一倍数
      - 字典：{A: 1.5, B: 3, C: 1, default: 0.9}
    优先级：类别键 > default > 1.0
    """
    if isinstance(self_loop_boost, (int, float)):
        return float(self_loop_boost)

    if not isinstance(self_loop_boost, dict):
        return 1.0

    default = float(self_loop_boost.get("default", 1.0))
    if target in a_set:
        return float(self_loop_boost.get("A", default))
    if target in b_set:
        return float(self_loop_boost.get("B", default))
    if target in c_set:
        return float(self_loop_boost.get("C", default))
    return default


# ============================================================
# 6.5 固定概率行构建（新增）
# ============================================================
def _build_row_with_fixed(
    row_module: str,
    fixed: Dict[str, float],
    cand,
    variant_counts: Dict[str, int],
    valid_columns: Set[str],
) -> Dict[str, float]:
    """
    构建一行概率：
    1. 固定值精确使用（不参与压缩/boost/归一化）
    2. 剩余百分比按行数比例分配给候选集里未固定的模块

    Returns: {模块名: 概率}
    """
    # 1. 过滤出有效的固定值
    fixed_weights = {}
    fixed_total = 0.0
    for m, p in fixed.items():
        if m in valid_columns:
            p = round(float(p), 2)
            fixed_weights[m] = p
            fixed_total += p

    if fixed_total > 100 + 1e-9:
        raise ValueError(
            f"模块 '{row_module}' 的 fixed_prob 总和 {fixed_total} 超过 100"
        )

    remaining = round(100 - fixed_total, 2)

    # 2. 确定剩余候选池（候选集 - 已固定的模块）
    if isinstance(cand, dict):
        cand_list = flatten_candidates(cand)
    elif isinstance(cand, list):
        cand_list = list(cand)
    else:
        cand_list = []

    remaining_pool = [
        m for m in cand_list
        if m not in fixed_weights and m in valid_columns
    ]

    row_probs = dict(fixed_weights)

    # 3. 剩余百分比分配
    if remaining > 0 and remaining_pool:
        # 按行数比例
        weights = {m: variant_counts.get(m, 0) for m in remaining_pool}
        total_w = sum(weights.values())

        if total_w > 0:
            exact = {m: (w / total_w) * remaining for m, w in weights.items()}
        else:
            # 行数全为 0，平均分配
            exact = {m: remaining / len(remaining_pool) for m in remaining_pool}

        # 最大余数法，保证剩余部分总和 = remaining（两位小数精确）
        floored = {m: math.floor(v * 100) / 100 for m, v in exact.items()}
        diff = round(remaining - sum(floored.values()), 2)

        if diff > 0:
            remainders = sorted(
                exact.keys(),
                key=lambda m: exact[m] - floored[m],
                reverse=True,
            )
            n = len(remainders)
            idx = 0
            while diff >= 0.01 - 1e-9:
                m = remainders[idx % n]
                floored[m] = round(floored[m] + 0.01, 2)
                diff = round(diff - 0.01, 2)
                idx += 1
                if idx > n * 2:
                    break

        row_probs.update(floored)
    # 若 remaining > 0 但 remaining_pool 为空，保留固定值，总和 < 100（会被 validate 提示）

    return row_probs


# ============================================================
# 7. 构建 prob 矩阵
# ============================================================
def _build_matrix(
    variant_counts: Dict[str, int],
    candidates: Dict,
    module_order: List[str],
    a_set: Set[str],
    b_set: Set[str],
    c_set: Set[str],
    compress_mode: str = "sqrt",
    boost: Dict[str, float] = None,
    self_loop_boost=1.0,
    self_loop_override: Dict[str, float] = None,
    fixed_prob: Dict[str, Dict[str, float]] = None,
) -> pd.DataFrame:
    boost = boost or {}
    self_loop_override = self_loop_override or {}
    fixed_prob = fixed_prob or {}

    def base_weight(target: str) -> float:
        """普通权重：压缩 + boost"""
        w = compress(variant_counts.get(target, 0), compress_mode)
        w *= boost.get(target, 1.0)
        return w

    def self_loop_weight(target: str) -> float:
        """自循环权重：普通权重 × 自循环倍数"""
        w = base_weight(target)
        if target in self_loop_override:
            w *= float(self_loop_override[target])
        else:
            w *= get_self_loop_multiplier(
                target, a_set, b_set, c_set, self_loop_boost
            )
        return w

    # A 类总权重：所有 A 的"自循环权重"之和
    a_total = sum(self_loop_weight(m) for m in a_set)

    matrix = pd.DataFrame(0.0, index=module_order, columns=module_order)
    valid_columns = set(matrix.columns)

    for row_module in module_order:
        cand = candidates[row_module]

        # ---- 优先级 1：fixed_prob（最高） ----
        fixed = fixed_prob.get(row_module, {})
        if fixed:
            row_probs = _build_row_with_fixed(
                row_module, fixed, cand, variant_counts, valid_columns
            )
            for m, p in row_probs.items():
                matrix.loc[row_module, m] = p
            continue

        # ---- 优先级 2：manual weights 模式 ----
        if isinstance(cand, dict) and "weights" in cand:
            weights = {m: w for m, w in cand["weights"].items() if m in valid_columns}
            if sum(weights.values()) <= 0:
                continue
            probs = normalize_to_100(weights)
            for m, p in probs.items():
                matrix.loc[row_module, m] = p
            continue

        # ---- 优先级 3：自动计算 ----
        cand_list = flatten_candidates(cand)
        if not cand_list:
            continue

        weights = {}
        for m in cand_list:
            if row_module in a_set and m == row_module:
                # A 类自循环：用整类总权重
                weights[m] = a_total
            elif m == row_module:
                # 非 A 类自循环：加自循环倍数
                weights[m] = self_loop_weight(m)
            else:
                weights[m] = base_weight(m)

        if sum(weights.values()) <= 0:
            continue

        probs = normalize_to_100(weights)
        for m, p in probs.items():
            if m in valid_columns:
                matrix.loc[row_module, m] = p

    return matrix


def build_prob_matrix(
    payload: dict,
    yaml_path: str,
    compress_mode: str = "sqrt",
) -> pd.DataFrame:
    variant_counts = payload["variant_counts"]
    candidates = payload["candidates"]
    fixed_prob = payload.get("fixed_prob", {}) or {}

    config = load_yaml_categories(yaml_path)
    all_keys = set(candidates.keys())

    a_set = set(config.get("A", []) or []) & all_keys
    b_set = set(config.get("B", []) or []) & all_keys
    c_set = set(config.get("C", []) or []) & all_keys
    module_order = get_module_order(config, candidates)

    # 从 YAML 读取业务偏好（全部可选）
    boost = config.get("boost", {}) or {}
    self_loop_boost = config.get("self_loop_boost", 1.0)
    self_loop_override = config.get("self_loop_boost_override", {}) or {}

    return _build_matrix(
        variant_counts, candidates, module_order,
        a_set, b_set, c_set,
        compress_mode=compress_mode,
        boost=boost,
        self_loop_boost=self_loop_boost,
        self_loop_override=self_loop_override,
        fixed_prob=fixed_prob,
    )


# ============================================================
# 8. 保存 Excel
# ============================================================
def save_prob_matrix(matrix: pd.DataFrame, output_path: str) -> str:
    dir_name = os.path.dirname(output_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        matrix.to_excel(writer, sheet_name="prob")
        workbook = writer.book
        worksheet = writer.sheets["prob"]

        num_fmt = workbook.add_format({"num_format": "0.00"})
        header_fmt = workbook.add_format({"bold": True})

        for col_num, value in enumerate(["模块"] + list(matrix.columns)):
            worksheet.write(0, col_num, value, header_fmt)
        for row in range(1, len(matrix) + 1):
            for col in range(1, len(matrix.columns) + 1):
                worksheet.write_number(row, col, matrix.iloc[row - 1, col - 1], num_fmt)

        worksheet.set_column(0, 0, 20)
        worksheet.set_column(1, len(matrix.columns), 10)

    return output_path


# ============================================================
# 9. 校验（容差收紧到 0.005）
# ============================================================
def validate_matrix(matrix: pd.DataFrame, threshold: float = 0.005) -> List[str]:
    issues = []
    for row_module in matrix.index:
        row_sum = matrix.loc[row_module].sum()
        if row_sum == 0:
            issues.append(f"行 '{row_module}' 全为 0（无出边）")
        elif abs(row_sum - 100) > threshold:
            issues.append(f"行 '{row_module}' 概率和为 {row_sum:.2f}，不等于 100")
    return issues