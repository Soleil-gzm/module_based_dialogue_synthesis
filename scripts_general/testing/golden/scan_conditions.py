"""
阶段 0 · 步骤 1：扫描话术 Excel，抽取 conditions(条件) 列全集 + 频次分布。

用法：
    cd scripts_general
    python -m testing.golden.scan_conditions \
        --excel "datas/suning/notdue_new/【生成式通用未逾期】电催话术通用模板-首催 - 20260826.xlsx" \
        --prob "datas/suning/notdue_new/0827.xlsx" \
        --output testing/golden/condition_inventory.json

输出：
    - JSON：{条件字符串: {count, sheets: [模块名]}}
    - 控制台：去重总数、Top 20 高频条件、出现空条件/NaN 的 sheet
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

import pandas as pd

# 让脚本能从 scripts_general/ 目录运行时找到 core 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def load_modules(prob_path: str) -> List[str]:
    """从 prob 表提取模块名（与 data_loader.load_prob_matrix 一致）"""
    prob_df = pd.read_excel(prob_path, header=0, index_col=0)
    modules = [str(m).strip() for m in prob_df.index]
    return modules


def normalize_condition(value: Any) -> str:
    """统一空值表示，便于去重统计"""
    if value is None:
        return "<空/NaN>"
    if isinstance(value, float) and pd.isna(value):
        return "<空/NaN>"
    s = str(value).strip()
    return s if s else "<空/NaN>"


def scan_excel(excel_path: str, modules: List[str]) -> Tuple[Dict[str, Dict], Dict[str, int]]:
    """
    返回：
        inventory: {条件字符串: {"count": int, "sheets": [模块名]}}
        sheet_stats: {模块名: 该 sheet 的总行数}
    """
    xls = pd.ExcelFile(excel_path)
    excel_sheets = set(xls.sheet_names)

    missing = [m for m in modules if m not in excel_sheets]
    if missing:
        xls.close()
        raise ValueError(f"Excel 缺少 prob 表要求的模块 sheet: {missing}")

    inventory: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "sheets": set()})
    sheet_stats: Dict[str, int] = {}

    for sheet in modules:
        df = pd.read_excel(xls, sheet_name=sheet)
        sheet_stats[sheet] = len(df)
        if "conditions(条件)" not in df.columns:
            # 该 sheet 没有条件列，按全部无条件处理
            inventory["<无该列>"]["count"] += len(df)
            inventory["<无该列>"]["sheets"].add(sheet)
            continue
        for raw in df["conditions(条件)"].tolist():
            cond = normalize_condition(raw)
            inventory[cond]["count"] += 1
            inventory[cond]["sheets"].add(sheet)

    xls.close()

    # set → list，便于 JSON 序列化
    inventory_out = {
        k: {"count": v["count"], "sheets": sorted(v["sheets"])}
        for k, v in inventory.items()
    }
    return inventory_out, sheet_stats


def print_summary(inventory: Dict[str, Dict], sheet_stats: Dict[str, int]) -> None:
    total_rows = sum(sheet_stats.values())
    total_unique = len(inventory)
    print(f"\n===== 条件字符串扫描报告 =====")
    print(f"扫描 sheet 数：{len(sheet_stats)}")
    print(f"话术总行数：{total_rows}")
    print(f"去重条件字符串数：{total_unique}")
    print(f"\n----- Top 20 高频条件 -----")
    sorted_items = sorted(inventory.items(), key=lambda x: -x[1]["count"])
    for cond, info in sorted_items[:20]:
        sheets_str = ", ".join(info["sheets"][:3])
        more = f" +{len(info['sheets'])-3}" if len(info["sheets"]) > 3 else ""
        display = cond if len(cond) <= 50 else cond[:47] + "..."
        print(f"  [{info['count']:>4}次 | {len(info['sheets'])}个sheet] {display}  ({sheets_str}{more})")

    print(f"\n----- 按条件结构归类（启发式）-----")
    categories = {
        "空/无条件": 0,
        "仅含'未逾期'": 0,
        "仅含'逾期'（非'未逾期'）": 0,
        "含'不为空'": 0,
        "含'为空'": 0,
        "含'{逾期天数}'": 0,
        "含'&'复合": 0,
    }
    for cond in inventory:
        if cond in ("<空/NaN>", "<无该列>"):
            categories["空/无条件"] += 1
            continue
        if "未逾期" in cond:
            categories["仅含'未逾期'"] += 1
        elif "逾期" in cond:
            categories["仅含'逾期'（非'未逾期'）"] += 1
        if "不为空" in cond:
            categories["含'不为空'"] += 1
        if "为空" in cond and "不为空" not in cond:
            categories["含'为空'"] += 1
        if "{逾期天数}" in cond:
            categories["含'{逾期天数}'"] += 1
        if "&" in cond:
            categories["含'&'复合"] += 1
    for cat, n in categories.items():
        print(f"  {cat}: {n}")

    print(f"\n----- 疑似异常值（含未知字段或格式）-----")
    # 按长度降序替换，避免 "逾期" 误吃 "逾期笔数" 里的子串
    known_tokens = sorted(
        [
            "未逾期", "逾期笔数", "逾期", "{逾期天数}",
            "小于", "等于", "大于",
            "总欠款", "本金", "利息", "罚息",
            "不为空", "为空", "&",
        ],
        key=len,
        reverse=True,
    )
    suspects = []
    for cond in inventory:
        if cond in ("<空/NaN>", "<无该列>"):
            continue
        tmp = cond
        for kw in known_tokens:
            tmp = tmp.replace(kw, " ")
        # 去数字后再看是否还有非空白残留
        digits_removed = "".join(c for c in tmp if not c.isdigit())
        if digits_removed.strip():
            suspects.append(cond)
    if suspects:
        for s in suspects[:20]:
            print(f"  ? {s}")
    else:
        print("  （无）")


def main():
    parser = argparse.ArgumentParser(description="扫描话术 Excel 条件列全集")
    parser.add_argument("--excel", required=True, help="话术模板 Excel 路径")
    parser.add_argument("--prob", required=True, help="prob 表 Excel 路径（用于确定模块名）")
    parser.add_argument("--output", default=None, help="输出 JSON 路径（默认不写文件）")
    args = parser.parse_args()

    modules = load_modules(args.prob)
    print(f"从 prob 表加载到 {len(modules)} 个模块: {modules}")

    inventory, sheet_stats = scan_excel(args.excel, modules)
    print_summary(inventory, sheet_stats)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        payload = {
            "excel_path": os.path.abspath(args.excel),
            "prob_path": os.path.abspath(args.prob),
            "sheet_stats": sheet_stats,
            "inventory": inventory,
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"\n全集已写入: {args.output}")


if __name__ == "__main__":
    main()
