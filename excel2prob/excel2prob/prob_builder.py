"""
生成 prob 概率表模块

公开接口：
    build_prob_matrix(payload, yaml_path, compress_mode) -> pd.DataFrame
    save_prob_matrix(matrix, output_path) -> str
    validate_matrix(matrix) -> List[str]

优先级：
    manual 字典模式  >  boost + self_loop  >  纯自动计算

业务偏好配置（全部可选，不写则行为不变）：
    boost:
        模块名: 倍数            # 单模块权重倍数
    self_loop_boost: 1.5        # 全局自循环倍数
    self_loop_boost_override:
        模块名: 倍数            # 单模块自循环倍数，覆盖全局

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

    # 精确百分比
    exact = {m: w / total * 100 for m, w in weights.items()}
    # 向下取整到 2 位小数
    floored = {m: math.floor(v * 100) / 100 for m, v in exact.items()}
    # 差额
    diff = round(100 - sum(floored.values()), 2)

    if diff <= 0:
        return floored

    # 按小数部分降序排序，依次补 0.01
    remainders = sorted(
        exact.keys(),
        key=lambda m: exact[m] - floored[m],
        reverse=True,
    )

    n = len(remainders)
    idx = 0
    # diff 最多是 n * 0.01，一轮即可覆盖，用取模兜底
    while diff >= 0.01 - 1e-9:
        m = remainders[idx % n]
        floored[m] = round(floored[m] + 0.01, 2)
        diff = round(diff - 0.01, 2)
        idx += 1
        if idx > n * 2:  # 保护，理论上不会触发
            break

    return floored


# ============================================================
# 6. 构建 prob 矩阵
# ============================================================
def _build_matrix(
    variant_counts: Dict[str, int],
    candidates: Dict,
    module_order: List[str],
    a_set: Set[str],
    compress_mode: str = "sqrt",
    boost: Dict[str, float] = None,
    self_loop_boost: float = 1.0,
    self_loop_override: Dict[str, float] = None,
) -> pd.DataFrame:
    boost = boost or {}
    self_loop_override = self_loop_override or {}

    def base_weight(target: str) -> float:
        """普通权重：压缩 + boost"""
        w = compress(variant_counts.get(target, 0), compress_mode)
        w *= boost.get(target, 1.0)
        return w

    def self_loop_weight(target: str) -> float:
        """自循环权重：普通权重 × 自循环倍数"""
        w = base_weight(target)
        w *= self_loop_override.get(target, self_loop_boost)
        return w

    # A 类总权重：所有 A 的"自循环权重"之和
    a_total = sum(self_loop_weight(m) for m in a_set)

    matrix = pd.DataFrame(0.0, index=module_order, columns=module_order)

    for row_module in module_order:
        cand = candidates[row_module]

        # ---- manual 字典模式：精确覆盖，走归一化 ----
        if isinstance(cand, dict) and "weights" in cand:
            weights = {m: w for m, w in cand["weights"].items() if m in matrix.columns}
            if sum(weights.values()) <= 0:
                continue
            probs = normalize_to_100(weights)
            for m, p in probs.items():
                matrix.loc[row_module, m] = p
            continue

        # ---- 普通模式：按 boost + self_loop 加成 ----
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
            if m in matrix.columns:
                matrix.loc[row_module, m] = p

    return matrix


def build_prob_matrix(
    payload: dict,
    yaml_path: str,
    compress_mode: str = "sqrt",
) -> pd.DataFrame:
    variant_counts = payload["variant_counts"]
    candidates = payload["candidates"]

    config = load_yaml_categories(yaml_path)
    a_set = set(config.get("A", []) or []) & set(candidates.keys())
    module_order = get_module_order(config, candidates)

    # 从 YAML 读取业务偏好（全部可选）
    boost = config.get("boost", {}) or {}
    self_loop_boost = float(config.get("self_loop_boost", 1.0))
    self_loop_override = config.get("self_loop_boost_override", {}) or {}

    return _build_matrix(
        variant_counts, candidates, module_order, a_set,
        compress_mode=compress_mode,
        boost=boost,
        self_loop_boost=self_loop_boost,
        self_loop_override=self_loop_override,
    )


# ============================================================
# 7. 保存 Excel
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
# 8. 校验（容差收紧到 0.005）
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