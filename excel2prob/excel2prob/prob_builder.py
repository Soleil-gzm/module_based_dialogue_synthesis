"""
生成 prob 概率表模块

公开接口：
    build_prob_matrix(payload, yaml_path, compress_mode) -> pd.DataFrame
    save_prob_matrix(matrix, output_path) -> str
    validate_matrix(matrix) -> List[str]
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
# 5. 构建 prob 矩阵
# ============================================================
def _build_matrix(
    variant_counts: Dict[str, int],
    candidates: Dict,
    module_order: List[str],
    a_set: Set[str],
    compress_mode: str = "sqrt"
) -> pd.DataFrame:
    matrix = pd.DataFrame(0.0, index=module_order, columns=module_order)

    a_total_compressed = sum(
        compress(variant_counts.get(m, 0), compress_mode) for m in a_set
    )

    for row_module in module_order:
        cand = candidates[row_module]

        # 分支 1：权重模式
        if isinstance(cand, dict) and "weights" in cand:
            weights = {m: w for m, w in cand["weights"].items() if m in matrix.columns}
            total = sum(weights.values())
            if total == 0:
                continue
            for m, w in weights.items():
                matrix.loc[row_module, m] = round(w / total * 100, 2)
            continue

        # 分支 2：按压缩 row 加权
        cand_list = flatten_candidates(cand)
        if not cand_list:
            continue

        weights = {}
        for m in cand_list:
            if row_module in a_set and m == row_module:
                weights[m] = a_total_compressed
            else:
                weights[m] = compress(variant_counts.get(m, 0), compress_mode)

        total = sum(weights.values())
        if total == 0:
            continue

        for m, w in weights.items():
            if m in matrix.columns:
                matrix.loc[row_module, m] = round(w / total * 100, 2)

    return matrix


def build_prob_matrix(
    payload: dict,
    yaml_path: str,
    compress_mode: str = "sqrt"
) -> pd.DataFrame:
    """
    从 candidates payload 构建 prob 矩阵。
    """
    variant_counts = payload["variant_counts"]
    candidates = payload["candidates"]

    config = load_yaml_categories(yaml_path)
    a_set = set(config.get("A", []) or []) & set(candidates.keys())
    module_order = get_module_order(config, candidates)

    return _build_matrix(
        variant_counts, candidates, module_order, a_set,
        compress_mode=compress_mode
    )


# ============================================================
# 6. 保存 Excel
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
# 7. 校验
# ============================================================
def validate_matrix(matrix: pd.DataFrame, threshold: float = 0.05) -> List[str]:
    issues = []
    for row_module in matrix.index:
        row_sum = matrix.loc[row_module].sum()
        if row_sum == 0:
            issues.append(f"行 '{row_module}' 全为 0（无出边）")
        elif abs(row_sum - 100) > threshold:
            issues.append(f"行 '{row_module}' 概率和为 {row_sum:.2f}，不等于 100")
    return issues