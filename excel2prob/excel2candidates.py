"""
话术统计 + 候选集生成脚本

流程：
    1. 读取话术 Excel，统计每个 sheet（模块）的 uid 行数
    2. 读取 YAML，生成每个模块的候选集
    3. 输出 JSON 到 intermediate/ 目录，文件名自动带时间戳

用法：
    python build_candidates.py
"""

import json
import os
from datetime import datetime
from typing import Dict, List

import pandas as pd
import yaml


# ============================================================
# 硬编码配置（改这里即可）
# ============================================================
EXCEL_PATH = "datas/suning_0909/due-0909/【生成式通用前端逾期】电催话术通用模板-首催-20260826.xlsx"              # 输入：话术 Excel
YAML_PATH = "excel2prob/config/categories.yaml"    # 输入：类别定义 YAML
OUTPUT_DIR = "intermediate"             # 输出目录
EXCLUDE_SHEETS = ["逻辑","Sheet1"]               # 不是话术模块的 sheet，跳过统计


# ============================================================
# 1. 统计 uid 行数
# ============================================================
def count_rows_from_excel(excel_path: str, exclude_sheets: List[str] = None) -> Dict[str, int]:
    """
    统计每个 sheet 的 uid 有效行数。
    - 跳过 EXCLUDE_SHEETS 里的 sheet
    - 过滤表头行（uid 列值为 "uid" 的行）
    - 过滤全空行
    """
    exclude_set = set(exclude_sheets or [])
    xls = pd.ExcelFile(excel_path)
    counts = {}

    for sheet_name in xls.sheet_names:
        if sheet_name in exclude_set:
            continue

        df = xls.parse(sheet_name)

        # 过滤表头行
        if "uid" in df.columns:
            df = df[df["uid"].astype(str) != "uid"]

        # 过滤全空行
        df = df.dropna(how="all")

        counts[sheet_name] = len(df)

    return counts


# ============================================================
# 2. 根据 YAML 生成候选集
# ============================================================
def build_candidates_from_yaml(yaml_path: str, variant_counts: Dict[str, int]) -> Dict[str, List[str]]:
    """
    规则：
        custom 里定义 → 用自定义列表
        excluded 里 → 空
        A 类 → [自身] + 所有 B
        B 类 / 未分类 → 所有 A + 所有 B
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    a_list = config.get("A", []) or []
    b_list = config.get("B", []) or []
    custom = config.get("custom", {}) or {}
    excluded = config.get("excluded", []) or []

    all_modules = set(variant_counts.keys())
    a_set = set(a_list) & all_modules
    b_set = set(b_list) & all_modules

    candidates = {}
    for module in all_modules:
        # 1. custom 优先
        if module in custom:
            candidates[module] = [m for m in custom[module] if m in all_modules]
        # 2. excluded
        elif module in excluded:
            candidates[module] = []
        # 3. A 类：自身 + 所有 B
        elif module in a_set:
            candidates[module] = [module] + sorted(b_set)
        # 4. B 类 / 未分类：所有 A + 所有 B
        else:
            candidates[module] = sorted(a_set) + sorted(b_set)

    return candidates


# ============================================================
# 3. 输出 JSON
# ============================================================
def export_candidates(
    variant_counts: Dict[str, int],
    candidates: Dict[str, List[str]],
    output_dir: str
) -> str:
    """自动建目录，自动命名（带时间戳），输出 JSON。"""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"candidates_{timestamp}.json")

    payload = {
        "generated_at": timestamp,
        "excel_path": EXCEL_PATH,
        "yaml_path": YAML_PATH,
        "variant_counts": variant_counts,
        "candidates": candidates,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return output_path


# ============================================================
# 主流程
# ============================================================
def main():
    # 检查输入文件
    if not os.path.exists(EXCEL_PATH):
        raise FileNotFoundError(f"话术表不存在: {EXCEL_PATH}")
    if not os.path.exists(YAML_PATH):
        raise FileNotFoundError(f"YAML 不存在: {YAML_PATH}")

    # 1. 统计
    print(f"[1/3] 读取话术表: {EXCEL_PATH}")
    variant_counts = count_rows_from_excel(EXCEL_PATH, EXCLUDE_SHEETS)
    print(f"      统计到 {len(variant_counts)} 个模块")
    for m, c in variant_counts.items():
        print(f"        {m}: {c} 行")

    # 2. 生成候选集
    print(f"\n[2/3] 读取 YAML: {YAML_PATH}")
    candidates = build_candidates_from_yaml(YAML_PATH, variant_counts)
    print(f"      生成 {len(candidates)} 个模块的候选集")

    # 3. 输出
    print(f"\n[3/3] 输出候选文件")
    output_path = export_candidates(variant_counts, candidates, OUTPUT_DIR)
    print(f"      {output_path}")

    # 预览
    print("\n候选集预览:")
    for m, cands in candidates.items():
        cands_str = ", ".join(cands) if cands else "(空)"
        print(f"  {m} ({variant_counts[m]}行) → {cands_str}")


if __name__ == "__main__":
    main()