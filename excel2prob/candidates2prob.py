"""
生成 prob 概率表（百分制，含压缩）

压缩方式：
    "none" → 原始 row 数，不压缩
    "sqrt" → 开方压缩（推荐起点）
    "log"  → 对数压缩（更均匀）
"""

import json
import math
import os
from datetime import datetime
from typing import Dict, List, Set, Union

import pandas as pd
import yaml


# ============================================================
# 硬编码配置（改这里即可）
# ============================================================
CANDIDATES_PATH = "intermediate/candidates_20260916_095303.json"
YAML_PATH = "excel2prob/config/categories.yaml"
OUTPUT_DIR = "intermediate/prob"
COMPRESS_MODE = "log"   # "none" / "sqrt" / "log"


# ============================================================
# 1. 读取输入
# ============================================================
def load_candidates(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml_categories(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ============================================================
# 2. 模块顺序：manual → A → B → C
# ============================================================
def get_module_order(config: dict, candidates: Dict) -> List[str]:
    """
    按 manual → A → B → C 的顺序返回模块列表。
    每组内保持 YAML 定义的顺序。
    """
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
def flatten_candidates(cand: Union[Dict[str, List[str]], List[str]]) -> List[str]:
    """
    普通模块 → 合并 A/B/C 三组，去重
    manual 模块 → 直接返回列表
    """
    if isinstance(cand, list):
        return cand
    result = []
    seen = set()
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
def build_prob_matrix(
    variant_counts: Dict[str, int],
    candidates: Dict[str, Union[Dict[str, List[str]], List[str]]],
    module_order: List[str],
    a_set: Set[str],
    compress_mode: str = "sqrt"
) -> pd.DataFrame:
    """
    对每一行：
        - 若该行是 A 类：A 组权重 = 所有 A 的 row 之和，全部赋给当前 A 模块自己
        - 若该行是 manual：按候选列表扁平处理
        - 否则（B/C）：每个候选模块用自己 row
    """
    matrix = pd.DataFrame(0.0, index=module_order, columns=module_order)

    # A 类总权重：先对每个 A 压缩，再求和
    a_total_compressed = sum(
        compress(variant_counts.get(m, 0), compress_mode) for m in a_set
    )

    for row_module in module_order:
        cand_list = flatten_candidates(candidates[row_module])
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


# ============================================================
# 6. 输出 Excel
# ============================================================
def export_prob_matrix(matrix: pd.DataFrame, output_dir: str, mode: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"prob_{mode}_{timestamp}.xlsx")

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        matrix.to_excel(writer, sheet_name="prob")
        workbook = writer.book
        worksheet = writer.sheets["prob"]

        # 数字格式：保留两位小数
        num_fmt = workbook.add_format({"num_format": "0.00"})
        # 表头加粗
        header_fmt = workbook.add_format({"bold": True})

        # 应用表头格式
        for col_num, value in enumerate(["模块"] + list(matrix.columns)):
            worksheet.write(0, col_num, value, header_fmt)

        # 应用数值格式
        for row in range(1, len(matrix) + 1):
            for col in range(1, len(matrix.columns) + 1):
                worksheet.write_number(row, col, matrix.iloc[row - 1, col - 1], num_fmt)

        # 列宽
        worksheet.set_column(0, 0, 20)
        worksheet.set_column(1, len(matrix.columns), 10)

    return output_path


# ============================================================
# 7. 校验
# ============================================================
def validate_matrix(matrix: pd.DataFrame, threshold: float = 0.05):
    """检查每行概率和是否为 100（非全 0 行）"""
    issues = []
    for row_module in matrix.index:
        row_sum = matrix.loc[row_module].sum()
        if row_sum == 0:
            issues.append(f"行 '{row_module}' 全为 0（无出边）")
        elif abs(row_sum - 100) > threshold:
            issues.append(f"行 '{row_module}' 概率和为 {row_sum:.2f}，不等于 100")
    return issues


# ============================================================
# 主流程
# ============================================================
def main():
    if not os.path.exists(CANDIDATES_PATH):
        raise FileNotFoundError(f"候选文件不存在: {CANDIDATES_PATH}")
    if not os.path.exists(YAML_PATH):
        raise FileNotFoundError(f"YAML 不存在: {YAML_PATH}")

    # 1. 读取
    data = load_candidates(CANDIDATES_PATH)
    variant_counts = data["variant_counts"]
    candidates = data["candidates"]
    # 2. 构建矩阵
    config = load_yaml_categories(YAML_PATH)
    a_set = set(config.get("A", []) or []) & set(candidates.keys())

    module_order = get_module_order(config, candidates)
    # 3. 输出
    matrix = build_prob_matrix(
        variant_counts, candidates, module_order, a_set,
        compress_mode=COMPRESS_MODE
    )
    output_path = export_prob_matrix(matrix, OUTPUT_DIR, COMPRESS_MODE)
    print(f"prob 文件: {output_path}  (压缩方式: {COMPRESS_MODE})")
    # 4. 校验
    issues = validate_matrix(matrix)
    if issues:
        print("\n校验提示:")
        for issue in issues:
            print(f"  ⚠️ {issue}")
    else:
        print("所有行概率和均为 100（百分制）")


if __name__ == "__main__":
    main()