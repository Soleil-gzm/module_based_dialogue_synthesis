"""
生成 prob 概率表（百分制）

表头顺序：manual → A → B → C（按 YAML 定义顺序）
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Union

import pandas as pd
import yaml


# ============================================================
# 硬编码配置（改这里即可）
# ============================================================
CANDIDATES_PATH = "intermediate/candidates_20260916_095303.json"   # 输入：候选文件
YAML_PATH = "excel2prob/config/categories.yaml"                                # 输入：类别定义 YAML
OUTPUT_DIR = "intermediate/prob"                                          # 输出目录


# ============================================================
# 1. 读取候选文件
# ============================================================
def load_candidates(candidates_path: str) -> dict:
    with open(candidates_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


# ============================================================
# 2. 从 YAML 获取模块排列顺序
# ============================================================
def get_module_order(yaml_path: str, candidates: Dict) -> List[str]:
    """
    按 manual → A → B → C 的顺序返回模块列表。
    每组内保持 YAML 定义的顺序。
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    order = []

    # manual
    for m in (config.get("manual", {}) or {}).keys():
        if m in candidates and m not in order:
            order.append(m)

    # A
    for m in config.get("A", []) or []:
        if m in candidates and m not in order:
            order.append(m)

    # B
    for m in config.get("B", []) or []:
        if m in candidates and m not in order:
            order.append(m)

    # C
    for m in config.get("C", []) or []:
        if m in candidates and m not in order:
            order.append(m)

    # 兜底：任何还没被收录的（理论上不会出现）
    for m in candidates:
        if m not in order:
            order.append(m)

    return order


# ============================================================
# 3. 把候选展平为列表
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
# 4. 构建 prob 矩阵（百分制）
# ============================================================
def build_prob_matrix(
    variant_counts: Dict[str, int],
    candidates: Dict[str, Union[Dict[str, List[str]], List[str]]],
    module_order: List[str]
) -> pd.DataFrame:
    """
    行、列都按 module_order 排列。
    对每个模块，按候选模块的 row 数归一化到百分制。
    """
    matrix = pd.DataFrame(0.0, index=module_order, columns=module_order)

    for row_module in module_order:
        cand_list = flatten_candidates(candidates[row_module])
        if not cand_list:
            continue

        weights = {m: variant_counts.get(m, 0) for m in cand_list}
        total = sum(weights.values())

        if total == 0:
            continue

        for m, w in weights.items():
            if m in matrix.columns:
                matrix.loc[row_module, m] = round(w / total * 100, 2)

    return matrix


# ============================================================
# 5. 输出 Excel（显式百分比格式）
# ============================================================
def export_prob_matrix(matrix: pd.DataFrame, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"prob_{timestamp}.xlsx")

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

        worksheet.set_column(0, 0, 20)
        worksheet.set_column(1, len(matrix.columns), 10)

    return output_path


# ============================================================
# 6. 校验
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
    module_order = get_module_order(YAML_PATH, candidates)
    print(f"模块顺序: manual({sum(1 for m in module_order[:len(candidates)])}) ...")
    print(f"总计 {len(module_order)} 个模块")
    # 3. 输出
    matrix = build_prob_matrix(variant_counts, candidates, module_order)
    output_path = export_prob_matrix(matrix, OUTPUT_DIR)
    print(f"prob 文件: {output_path}")
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