"""
话术统计 + 候选集生成模块

公开接口：
    build_candidates(excel_path, yaml_path) -> dict
    save_candidates(payload, output_path) -> str
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Union

import pandas as pd
import yaml


# ============================================================
# 1. 统计 uid 行数
# ============================================================
def count_rows_from_excel(excel_path: str) -> Dict[str, int]:
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
# 2. 展开列表模式
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
# 3. 展开字典模式（权重）
# ============================================================
def expand_manual_weights(
    raw_dict: dict,
    a_set: set,
    b_set: set,
    c_set: set,
    all_modules: set,
    variant_counts: Dict[str, int],
) -> Dict[str, float]:
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
# 4. 从 YAML 生成候选集
# ============================================================
def build_candidates_from_yaml(
    yaml_path: str, variant_counts: Dict[str, int]
) -> Dict[str, Union[Dict[str, List[str]], List[str]]]:
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

    # manual
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

    # A 类
    for module in sorted(a_set):
        if module in candidates:
            continue
        candidates[module] = {
            "A": [module],
            "B": sorted(b_set),
            "C": sorted(c_set),
        }

    # B 类
    for module in sorted(b_set):
        if module in candidates:
            continue
        candidates[module] = {
            "A": sorted(a_set),
            "B": sorted(b_set),
            "C": sorted(c_set),
        }

    # C 类
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
# 5. 端到端：构建 payload
# ============================================================
def build_candidates(excel_path: str, yaml_path: str) -> dict:
    """
    读 excel + yaml，返回完整 payload
    （含 variant_counts、candidates、fixed_prob、unused_modules）
    """
    variant_counts = count_rows_from_excel(excel_path)
    candidates = build_candidates_from_yaml(yaml_path, variant_counts)

    # 读取 fixed_prob
    with open(yaml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    fixed_prob = config.get("fixed_prob", {}) or {}

    used_modules = set(candidates.keys())
    all_modules = set(variant_counts.keys())
    unused_modules = sorted(all_modules - used_modules)

    return {
        "generated_at": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "excel_path": excel_path,
        "yaml_path": yaml_path,
        "variant_counts": variant_counts,
        "candidates": candidates,
        "fixed_prob": fixed_prob,
        "unused_modules": unused_modules,
    }


# ============================================================
# 6. 保存候选文件
# ============================================================
def save_candidates(payload: dict, output_path: str) -> str:
    dir_name = os.path.dirname(output_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return output_path
