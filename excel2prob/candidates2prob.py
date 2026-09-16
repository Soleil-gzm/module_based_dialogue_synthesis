"""
生成 prob 概率表（百分制）

流程：
    1. 读取 candidates.json
    2. 对每个模块，取其候选模块的 row 数
    3. 按 row 数归一化，输出为百分制（0~100）
    4. 输出为 Excel，每行概率和 = 100
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Union

import pandas as pd


# ============================================================
# 硬编码配置（改这里即可）
# ============================================================
CANDIDATES_PATH = "intermediate/candidates_20260916_095303.json"   # 输入：候选文件
OUTPUT_DIR = "intermediate/prob"                                          # 输出目录


# ============================================================
# 1. 读取候选文件
# ============================================================
def load_candidates(candidates_path: str) -> dict:
    with open(candidates_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


# ============================================================
# 2. 把候选展平为列表
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
# 3. 构建 prob 矩阵（百分制）
# ============================================================
def build_prob_matrix(
    variant_counts: Dict[str, int],
    candidates: Dict[str, Union[Dict[str, List[str]], List[str]]]
) -> pd.DataFrame:
    """
    对每个模块，按候选模块的 row 数归一化，结果以百分制表示。
    每行概率之和 = 100。
    """
    modules = sorted(candidates.keys())
    matrix = pd.DataFrame(0.0, index=modules, columns=modules)

    for row_module in modules:
        cand_list = flatten_candidates(candidates[row_module])
        if not cand_list:
            continue

        weights = {m: variant_counts.get(m, 0) for m in cand_list}
        total = sum(weights.values())

        if total == 0:
            continue

        for m, w in weights.items():
            matrix.loc[row_module, m] = round(w / total * 100, 2)

    return matrix


# ============================================================
# 4. 输出 Excel（显式百分比格式）
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

        # 列宽
        worksheet.set_column(0, 0, 20)
        worksheet.set_column(1, len(matrix.columns), 10)

    return output_path


# ============================================================
# 5. 校验
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

    # 1. 读取
    data = load_candidates(CANDIDATES_PATH)
    variant_counts = data["variant_counts"]
    candidates = data["candidates"]

    # 2. 构建矩阵
    matrix = build_prob_matrix(variant_counts, candidates)

    # 3. 输出
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