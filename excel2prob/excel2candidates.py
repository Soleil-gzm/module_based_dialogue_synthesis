"""
话术统计 + 候选集生成脚本

流程：
    1. 读取话术 Excel，统计每个 sheet（模块）的 uid 行数
    2. 读取 YAML，按 A/B/C/manual 四类生成候选集
    3. 输出 JSON 到 intermediate/ 目录，文件名自动带时间戳

YAML 结构：
    A: [模块1, 模块2, ...]       # 自循环类，路径中只出现一次
    B: [模块1, 模块2, ...]       # 可跳转类
    C: [模块1, 模块2, ...]       # 通用模块，A 和 B 都能跳转
    manual:                     # 手动模块，完全自定义候选
      模块名:
        - 候选1
        - A                     # 关键字：展开为所有 A 类模块
        - B                     # 关键字：展开为所有 B 类模块
        - C                     # 关键字：展开为所有 C 类模块

候选规则：
    A 类模块 → A组=[自身],        B组=所有B, C组=所有C
    B 类模块 → A组=所有A,          B组=所有B, C组=所有C
    C 类模块 → A组=所有A,          B组=所有B, C组=所有C
    未分类模块 → 按 B 类规则
    manual 模块 → 扁平列表（支持 A/B/C 关键字展开）

输出格式：
    普通模块 → {"A": [...], "B": [...], "C": [...]}
    manual 模块 → ["候选1", "候选2", ...]
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

        if "uid" in df.columns:
            df = df[df["uid"].astype(str) != "uid"]

        df = df.dropna(how="all")

        counts[sheet_name] = len(df)

    return counts


# ============================================================
# 2. 展开 manual 候选（支持 A/B/C 关键字）
# ============================================================
def expand_manual_candidates(
    raw_list: List[str],
    a_set: set,
    b_set: set,
    c_set: set,
    all_modules: set
) -> List[str]:
    """
    展开 manual 候选列表：
        - "A" → 所有 A 类模块
        - "B" → 所有 B 类模块
        - "C" → 所有 C 类模块
        - 其他字符串 → 作为普通模块名
    结果去重，并过滤掉不在话术表里的模块。
    """
    category_map = {
        "A": a_set,
        "B": b_set,
        "C": c_set,
    }

    result = []
    seen = set()
    for item in raw_list:
        if item in category_map:
            members = sorted(category_map[item])
        else:
            members = [item]

        for m in members:
            if m in all_modules and m not in seen:
                seen.add(m)
                result.append(m)

    return result


# ============================================================
# 3. 根据 YAML 生成候选集
# ============================================================
def build_candidates_from_yaml(
    yaml_path: str,
    variant_counts: Dict[str, int]
) -> Dict[str, Union[Dict[str, List[str]], List[str]]]:
    """
    规则：
        manual 模块 → 扁平列表（支持 A/B/C 关键字展开）
        A 类 → {"A": [自身],  "B": 所有B, "C": 所有C}
        B 类 → {"A": 所有A,   "B": 所有B, "C": 所有C}
        C 类 → {"A": 所有A,   "B": 所有B, "C": 所有C}
        未分类 → 按 B 类规则
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
    for module in all_modules:
        # 1. manual 优先：展开关键字，输出扁平列表
        if module in manual:
            candidates[module] = expand_manual_candidates(
                manual[module], a_set, b_set, c_set, all_modules
            )
            continue

        # 2. A 类：自身 + 所有 B + 所有 C
        if module in a_set:
            candidates[module] = {
                "A": [module],
                "B": sorted(b_set),
                "C": sorted(c_set),
            }
            continue

        # 3. B、C、未分类：所有 A + 所有 B + 所有 C
        candidates[module] = {
            "A": sorted(a_set),
            "B": sorted(b_set),
            "C": sorted(c_set),
        }

    return candidates


# ============================================================
# 4. 输出 JSON
# ============================================================
def export_candidates(
    variant_counts: Dict[str, int],
    candidates: Dict[str, Union[Dict[str, List[str]], List[str]]],
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
    for m, cand in candidates.items():
        if isinstance(cand, list):
            cand_str = ", ".join(cand) if cand else "(空)"
            print(f"  [manual] {m} ({variant_counts[m]}行) → [{cand_str}]")
        else:
            parts = []
            for cat in ("A", "B", "C"):
                if cand[cat]:
                    parts.append(f"{cat}=[{', '.join(cand[cat])}]")
            parts_str = " | ".join(parts) if parts else "(空)"
            print(f"  {m} ({variant_counts[m]}行) → {parts_str}")


if __name__ == "__main__":
    main()