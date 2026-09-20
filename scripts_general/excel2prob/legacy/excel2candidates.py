"""
话术统计 + 候选集生成脚本

流程：
    1. 读取话术 Excel，统计所有 sheet（模块）的 uid 行数
    2. 读取 YAML，按 A/B/C/manual 生成候选集
    3. 输出 JSON 到 intermediate/ 目录，文件名自动带时间戳
    4. 终端只输出未使用模块的提示

YAML 结构：
    A: [模块1, 模块2, ...]       # 自循环类
    B: [模块1, 模块2, ...]       # 可跳转类
    C: [模块1, 模块2, ...]       # 通用模块
    manual:
      模块名1:                    # 列表模式（展开 A/B/C 关键字，按 row 数加权）
        - 模块A
        - A
        - B
      模块名2:                    # 字典模式（手动指定权重，其余为 0）
        模块A: 15
        模块B: 70
        模块C: 15
      模块名3:                    # 混合模式：字典里也可以有 A/B/C 关键字
        自身: 20
        A: 30
        B: 50

输出结构：
    普通模块 → {"A": [...], "B": [...], "C": [...]}
    manual 列表模式 → ["候选1", "候选2", ...]
    manual 字典模式 → {"weights": {"模块": 权重, ...}}
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
EXCEL_PATH = "datas/suning_0909/due-0909/【生成式通用前端逾期】电催话术通用模板-首催-20260826.xlsx"  # 输入：话术 Excel
YAML_PATH = "excel2prob/config/categories.yaml"  # 输入：类别定义 YAML
OUTPUT_DIR = "intermediate"  # 输出目录


# ============================================================
# 1. 统计 uid 行数（所有 sheet）
# ============================================================
def count_rows_from_excel(excel_path: str) -> Dict[str, int]:
    """
    统计所有 sheet 的 uid 有效行数。
    - 过滤表头行（uid 列值为 "uid" 的行）
    - 过滤全空行
    """
    xls = pd.ExcelFile(excel_path)
    counts = {}

    for sheet_name in xls.sheet_names:
        df = xls.parse(sheet_name)
        if "uid" in df.columns:
            df = df[df["uid"].astype(str) != "uid"]
        df = df.dropna(how="all")
        counts[sheet_name] = len(df)

    return counts


# ============================================================
# 2. 展开列表模式的 manual 候选
# ============================================================
def expand_manual_list(
    raw_list: List[str], a_set: set, b_set: set, c_set: set, all_modules: set
) -> List[str]:
    category_map = {"A": a_set, "B": b_set, "C": c_set}
    result, seen = [], set()
    for item in raw_list:
        members = sorted(category_map[item]) if item in category_map else [item]
        for m in members:
            if m in all_modules and m not in seen:
                seen.add(m)
                result.append(m)
    return result


# ============================================================
# 3. 处理字典模式的 manual 候选
# ============================================================
def expand_manual_weights(
    raw_dict: dict,
    a_set: set,
    b_set: set,
    c_set: set,
    all_modules: set,
    variant_counts: Dict[str, int],
) -> Dict[str, float]:
    """
    字典模式：手动指定权重。
    - 普通键（模块名）→ 直接用其值作为权重
    - 关键字 A/B/C → 展开为该类所有模块，按各自 row 数分摊该值
    返回：{模块名: 权重}
    """
    category_map = {"A": a_set, "B": b_set, "C": c_set}
    weights = {}

    for key, val in raw_dict.items():
        val = float(val)

        if key in category_map:
            members = [m for m in category_map[key] if m in all_modules]
            if not members:
                continue
            total_row = sum(variant_counts.get(m, 0) for m in members)
            if total_row == 0:
                per = val / len(members)
                for m in members:
                    weights[m] = weights.get(m, 0) + per
            else:
                for m in members:
                    share = val * variant_counts.get(m, 0) / total_row
                    weights[m] = weights.get(m, 0) + share
        else:
            if key in all_modules:
                weights[key] = weights.get(key, 0) + val

    return weights


# ============================================================
# 4. 根据 YAML 生成候选集
# ============================================================
def build_candidates_from_yaml(
    yaml_path: str, variant_counts: Dict[str, int]
) -> Dict[str, Union[Dict[str, List[str]], List[str]]]:
    """
    只对 YAML 中定义的模块生成候选集。
    规则：
        manual 模块 → 扁平列表（支持 A/B/C 关键字展开）
        A 类 → {"A": [自身],  "B": 所有B, "C": 所有C}
        B 类 → {"A": 所有A,   "B": 所有B, "C": 所有C}
        C 类 → {"A": 所有A,   "B": 所有B, "C": 所有C}
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    a_list = config.get("A", []) or []
    b_list = config.get("B", []) or []
    c_list = config.get("C", []) or []
    manual = config.get("manual", {}) or {}

    all_modules = set(variant_counts.keys())
    a_set = set(a_list) & all_modules
    b_set = set(b_list) & all_modules
    c_set = set(c_list) & all_modules

    candidates = {}

    # 1. manual 模块（优先处理）
    for module, raw_entry in manual.items():
        if module not in all_modules:
            continue
        if isinstance(raw_entry, dict):
            weights = expand_manual_weights(
                raw_entry, a_set, b_set, c_set, all_modules, variant_counts
            )
            candidates[module] = {"weights": weights}
        else:
            expanded = expand_manual_list(raw_entry, a_set, b_set, c_set, all_modules)
            candidates[module] = expanded

    # 2. A 类模块
    for module in sorted(a_set):
        if module in candidates:
            continue
        candidates[module] = {
            "A": [module],
            "B": sorted(b_set),
            "C": sorted(c_set),
        }

    # 3. B 类模块
    for module in sorted(b_set):
        if module in candidates:
            continue
        candidates[module] = {
            "A": sorted(a_set),
            "B": sorted(b_set),
            "C": sorted(c_set),
        }

    # 4. C 类模块
    for module in sorted(c_set):
        if module in candidates:
            continue
        candidates[module] = {
            "A": sorted(a_set),
            "B": sorted(b_set),
            "C": sorted(c_set),
        }

    return candidates


# ============================================================
# 5. 输出 JSON
# ============================================================
def export_candidates(
    variant_counts: Dict[str, int], candidates: Dict, output_dir: str
) -> str:
    """自动建目录，自动命名（带时间戳），输出 JSON。"""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"candidates_{timestamp}.json")

    # 未使用模块 = 话术表里有，但 YAML 未定义
    used_modules = set(candidates.keys())
    all_modules = set(variant_counts.keys())
    unused_modules = sorted(all_modules - used_modules)

    payload = {
        "generated_at": timestamp,
        "excel_path": EXCEL_PATH,
        "yaml_path": YAML_PATH,
        "variant_counts": variant_counts,
        "candidates": candidates,
        "unused_modules": unused_modules,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return output_path, unused_modules


# ============================================================
# 主流程
# ============================================================
def main():
    if not os.path.exists(EXCEL_PATH):
        raise FileNotFoundError(f"话术表不存在: {EXCEL_PATH}")
    if not os.path.exists(YAML_PATH):
        raise FileNotFoundError(f"YAML 不存在: {YAML_PATH}")

    variant_counts = count_rows_from_excel(EXCEL_PATH)
    candidates = build_candidates_from_yaml(YAML_PATH, variant_counts)
    output_path, unused_modules = export_candidates(
        variant_counts, candidates, OUTPUT_DIR
    )

    print(f"候选文件: {output_path}")

    if unused_modules:
        print("\n未使用模块（在话术表中，但 YAML 未定义）:")
        for m in unused_modules:
            print(f"  {m} ({variant_counts[m]}行)")
    else:
        print("所有话术模块均已在 YAML 中使用")


if __name__ == "__main__":
    main()
