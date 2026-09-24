#!/usr/bin/env python3
"""
数据检测报告（Coverage Check）工具

用途：每次拿到新业务数据（Excel 话术模板 + 生成的 trace）后，
快速对照"Excel 定义了哪些模块/条件" vs "trace 实际用了哪些"，
判断当前代码与配置能否匹配这批数据。

用法:
  python analyze_coverage.py <trace.json> --excel <excel_path> [--prob <prob_path>]

输出:
  coverage_report_{timestamp}.txt，默认保存到 trace 同级的 analysis/ 目录。
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

# prob 表未定义、需要从 Excel sheet 名推断模块时排除的已知非模块 sheet
KNOWN_EXTRA_SHEETS = {"链接施压话术", "链接话术", "逻辑"}

# Excel 话术模板中需要读取的列
_NEED_COLS = ["uid", "conditions(条件)"]


def _detect_engine():
    """优先 calamine（与 data_loader 一致，免疫损坏的 AutoFilter）；
    缺失时回退到 pandas 默认引擎（openpyxl），保证脚本可用。"""
    try:
        import calamine  # noqa: F401
        return "calamine"
    except ImportError:
        return None


_ENGINE = _detect_engine()


def normalize_condition(s) -> str:
    """条件归一化：None/NaN/空串/'无条件' → '无条件(空)'，其余 str(s).strip()。
    Excel 端与 trace 端共用，确保两端对比基准一致。
    """
    if s is None:
        return "无条件(空)"
    try:
        if pd.isna(s):
            return "无条件(空)"
    except (TypeError, ValueError):
        pass
    s = str(s).strip()
    if s == "" or s == "无条件":
        return "无条件(空)"
    return s


def _extract_timestamp(trace_path: str) -> str:
    """从 trace 文件名提取时间戳，失败则用文件修改时间。"""
    import re
    import time

    basename = os.path.basename(trace_path)
    match = re.search(r"traces_(\d{8}_\d{6})\.json", basename)
    if match:
        return match.group(1)
    try:
        return time.strftime("%Y%m%d_%H%M%S", time.localtime(os.path.getmtime(trace_path)))
    except OSError:
        return time.strftime("%Y%m%d_%H%M%S")


def _get_modules_from_prob(prob_path: str):
    """从 prob 表提取 modules 列表（权威来源）。失败返回 None。"""
    try:
        prob_df = pd.read_excel(prob_path, header=0, index_col=0, engine=_ENGINE)
        prob_df.index = [str(m).strip() if pd.notna(m) else "" for m in prob_df.index]
        valid = [m for m in prob_df.index if m and m.lower() != "nan"]
        return valid
    except Exception:
        return None


def _get_modules_from_excel(excel_path: str):
    """无 prob 表时，从 Excel sheet 名推断 modules（排除已知非模块 sheet）。"""
    try:
        xls = pd.ExcelFile(excel_path, engine=_ENGINE)
        sheets = list(xls.sheet_names)
        xls.close()
        return [s for s in sheets if s not in KNOWN_EXTRA_SHEETS]
    except Exception:
        return None


def _load_module_sheets(excel_path: str, modules):
    """逐 sheet 读取 Excel 模块数据。
    与 data_loader.load_sheets 不同：缺失模块不抛错，记入 missing_modules。
    返回 (sheet_df_dict, missing_modules)。
    """
    sheet_df_dict = {}
    missing_modules = []
    xls = pd.ExcelFile(excel_path, engine=_ENGINE)
    available = set(xls.sheet_names)
    for m in modules:
        if m not in available:
            missing_modules.append(m)
            continue
        try:
            df = pd.read_excel(excel_path, sheet_name=m, engine=_ENGINE)
            # 只保留存在的列，避免 KeyError
            cols = [c for c in _NEED_COLS if c in df.columns]
            sheet_df_dict[m] = df[cols].copy() if cols else df.copy()
        except Exception:
            missing_modules.append(m)
    xls.close()
    return sheet_df_dict, missing_modules


def _collect_excel_conditions(df) -> dict:
    """从单个模块 sheet 收集条件全集。
    返回 {normalized_cond: [uid, uid, ...]}，uid 去重保序。
    若 conditions(条件) 列缺失，返回 {"<无法读取条件列>": []}。
    """
    result = defaultdict(list)
    cond_col = "conditions(条件)"
    if cond_col not in df.columns:
        return {"<Excel无'conditions(条件)'列>": []}
    has_uid = "uid" in df.columns
    for _, row in df.iterrows():
        raw = row.get(cond_col)
        cond = normalize_condition(raw)
        if has_uid:
            uid = row.get("uid")
            try:
                if pd.notna(uid):
                    uid = int(uid)
                else:
                    uid = None
            except (TypeError, ValueError):
                uid = uid  # 保留原始值
            if uid is not None and uid not in result[cond]:
                result[cond].append(uid)
        else:
            # 无 uid 列时，仅保证条件存在
            if not result[cond]:
                result[cond] = []
    return dict(result)


def _collect_trace_usage(traces):
    """统计 trace 中各模块的条件使用情况。
    仅 status=='processed' 且 selected_uid 非空计入。
    返回 {module_name: {normalized_cond: used_count}}。
    """
    usage = defaultdict(lambda: defaultdict(int))
    trace_modules_seen = set()  # 所有出现在 trace 里的模块名（含 skipped）
    for trace in traces:
        for mod in trace.get("modules", []):
            mname = mod.get("module")
            if mname is None:
                continue
            trace_modules_seen.add(mname)
            if mod.get("status") != "processed":
                continue
            if mod.get("selected_uid") in (None, -1, -1.0):
                continue
            cond_raw = mod.get("condition_text", "")
            cond = normalize_condition(cond_raw)
            usage[mname][cond] += 1
    # 转为普通 dict
    return {m: dict(c) for m, c in usage.items()}, trace_modules_seen


def _fmt_uid_list(uids):
    """格式化 uid 列表用于报告。"""
    if not uids:
        return "[]"
    if len(uids) <= 8:
        return "[" + ",".join(str(u) for u in uids) + "]"
    return "[" + ",".join(str(u) for u in uids[:8]) + f",...(共{len(uids)}个)]"


def analyze_coverage(trace_path, excel_path, prob_path=None, output_dir=None):
    """主函数：生成数据检测报告 TXT，返回报告路径。"""
    with open(trace_path, "r", encoding="utf-8") as f:
        traces = json.load(f)

    # ---- modules 全集 ----
    modules = None
    modules_source = "未知"
    prob_missing = True
    if prob_path:
        modules = _get_modules_from_prob(prob_path)
        if modules:
            modules_source = "prob表"
            prob_missing = False
    if not modules:
        modules = _get_modules_from_excel(excel_path)
        if modules:
            modules_source = "Excel推断"
    if not modules:
        raise RuntimeError("无法获取模块全集：prob 表和 Excel sheet 推断均失败。")

    # ---- 加载 Excel 模块 sheet（缺失不中断）----
    sheet_df_dict, missing_excel_modules = _load_module_sheets(excel_path, modules)

    # ---- Excel 端条件全集 ----
    excel_conditions = {}  # {module: {cond: [uids]}}
    for m in modules:
        df = sheet_df_dict.get(m)
        if df is None:
            excel_conditions[m] = None  # sheet 缺失
            continue
        excel_conditions[m] = _collect_excel_conditions(df)

    # ---- trace 端使用情况 ----
    trace_usage, trace_modules_seen = _collect_trace_usage(traces)

    # ---- 异常检测 ----
    modules_set = set(modules)
    trace_only_modules = sorted(trace_modules_seen - modules_set)
    trace_only_conditions = defaultdict(list)  # {module: [cond]}
    for m, conds in trace_usage.items():
        excel_conds = excel_conditions.get(m)
        if not excel_conds:
            # Excel 没有该模块或 sheet 缺失 → 所有 trace 条件都算异常
            if excel_conds is None:  # sheet 缺失，不算 trace_only_conditions
                continue
            for c in conds:
                if c not in excel_conds:
                    trace_only_conditions[m].append(c)
            continue
        for c in conds:
            if c not in excel_conds:
                trace_only_conditions[m].append(c)

    # ---- 统计 ----
    used_modules = []
    unused_modules = []
    for m in modules:
        if m in trace_usage and trace_usage[m]:
            used_modules.append(m)
        else:
            unused_modules.append(m)

    unused_cond_count = 0
    for m in modules:
        ec = excel_conditions.get(m)
        if not ec:
            continue
        for c in ec:
            if c not in trace_usage.get(m, {}):
                unused_cond_count += 1

    # ---- 写报告 ----
    import time

    gen_time = time.strftime("%Y-%m-%d %H:%M:%S")
    timestamp = _extract_timestamp(trace_path)

    if output_dir is None:
        output_dir = str(Path(trace_path).parent.parent / "analysis")
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, f"coverage_report_{timestamp}.txt")

    lines = []
    W = 78
    lines.append("=" * W)
    lines.append("数据检测报告 (Coverage Check)")
    lines.append("=" * W)
    lines.append(f"生成时间: {gen_time}")
    lines.append(f"Excel:    {excel_path}")
    lines.append(f"Trace:    {trace_path}  ({len(traces)} 条对话)")
    lines.append(
        f"模块全集来源: {modules_source}  (共 {len(modules)} 个模块)"
    )
    if prob_path:
        lines.append(f"prob表:   {prob_path}  ({'缺失' if prob_missing else '正常'})")
    lines.append("")

    # ===== 一、模块使用总览 =====
    lines.append(
        f"【一、模块使用总览】 Excel定义 {len(modules)} | 使用 {len(used_modules)} | 未使用 {len(unused_modules)}"
    )
    lines.append("-" * W)
    for m in modules:
        ec = excel_conditions.get(m)
        excel_cond_n = len(ec) if ec else 0
        used_conds = trace_usage.get(m, {})
        trace_cond_n = len(used_conds)
        if ec is None:
            cov_str = "N/A"
            mark = "✗"
            extra = "⚠ Excel sheet缺失"
        elif excel_cond_n == 0:
            cov_str = "N/A"
            mark = "·"
            extra = "Excel无条件定义"
        else:
            cov = trace_cond_n / excel_cond_n
            cov_str = f"{cov:.0%}"
            if trace_cond_n == 0:
                mark = "✗"
                extra = "⚠ 完全未使用"
            elif cov < 1.0:
                mark = "△"
                extra = f"部分使用(缺{excel_cond_n - trace_cond_n}条件)"
            else:
                mark = "✓"
                extra = ""
        lines.append(
            f"  [{mark}] {m:<14} Excel条件={excel_cond_n:<4} trace命中={trace_cond_n:<4} 覆盖率 {cov_str:>5}  {extra}"
        )
    lines.append("-" * W)
    if unused_modules:
        lines.append(f"未使用模块 ({len(unused_modules)}): {'、'.join(unused_modules)}")
    else:
        lines.append("未使用模块 (0): 所有模块均被使用 ✓")
    lines.append("")

    # ===== 二、每模块条件覆盖详情 =====
    lines.append("【二、每模块条件覆盖详情】")
    lines.append("-" * W)
    for m in modules:
        ec = excel_conditions.get(m)
        used_conds = trace_usage.get(m, {})
        if ec is None:
            lines.append(f"[{m}] Excel sheet 缺失，无法统计条件")
            lines.append("-" * W)
            continue
        excel_cond_n = len(ec)
        trace_cond_n = len(used_conds)
        unused_n = excel_cond_n - trace_cond_n
        lines.append(
            f"[{m}] Excel条件={excel_cond_n}  trace命中={trace_cond_n}  未使用={unused_n}"
        )
        if excel_cond_n == 0:
            lines.append("  · Excel 未定义任何条件")
            lines.append("-" * W)
            continue
        # 已使用条件（按 trace 出现次数降序）
        used_sorted = sorted(
            used_conds.items(), key=lambda x: x[1], reverse=True
        )
        for cond, cnt in used_sorted:
            uids = ec.get(cond, [])
            lines.append(
                f"  ✓ {cond:<26} trace出现 {cnt:>5} 次  Excel对应uid={_fmt_uid_list(uids)}"
            )
        # 未使用条件
        unused_conds = [c for c in ec if c not in used_conds]
        for cond in unused_conds:
            uids = ec.get(cond, [])
            lines.append(
                f"  ✗ {cond:<26} Excel定义但trace未出现  Excel对应uid={_fmt_uid_list(uids)}   ⚠"
            )
        lines.append("-" * W)

    # ===== 三、异常检测 =====
    lines.append("【三、异常检测】")
    lines.append("-" * W)
    # trace 有但 modules 全集无的模块
    if trace_only_modules:
        lines.append(
            f"trace有但Excel/prob无的模块 ({len(trace_only_modules)} 个): {'、'.join(trace_only_modules)}"
        )
    else:
        lines.append("trace有但Excel/prob无的模块 (0 个): -")
    # trace 有但 Excel 无的条件
    total_trace_only_cond = sum(len(v) for v in trace_only_conditions.values())
    if total_trace_only_cond:
        lines.append(f"trace有但Excel无的条件 ({total_trace_only_cond} 个):")
        for m, conds in sorted(trace_only_conditions.items()):
            for c in conds:
                lines.append(f"    {m} :: {c}")
    else:
        lines.append("trace有但Excel无的条件 (0 个): -")
    # Excel 缺失模块 sheet
    if missing_excel_modules:
        lines.append(
            f"Excel缺失模块sheet ({len(missing_excel_modules)} 个): {'、'.join(missing_excel_modules)}"
        )
    else:
        lines.append("Excel缺失模块sheet (0 个): -")
    lines.append(f"prob表缺失: {'是' if prob_missing else '否'}")
    lines.append("=" * W)

    # ===== 判定 =====
    alerts = []
    if unused_modules:
        alerts.append(f"{len(unused_modules)} 个模块未使用")
    if unused_cond_count:
        alerts.append(f"{unused_cond_count} 个条件未使用")
    if trace_only_modules:
        alerts.append(f"{len(trace_only_modules)} 个模块在trace但不在Excel/prob")
    if total_trace_only_cond:
        alerts.append(f"{total_trace_only_cond} 个条件在trace但不在Excel")
    if missing_excel_modules:
        alerts.append(f"{len(missing_excel_modules)} 个Excel sheet缺失")
    if alerts:
        lines.append("判定: " + "、".join(alerts) + " → 建议检查配置/路径生成")
    else:
        lines.append("判定: ✅ 全部模块与条件均匹配使用，无异常")
    lines.append("=" * W)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ 数据检测报告已生成: {report_path}")
    return report_path


def main():
    parser = argparse.ArgumentParser(description="数据检测报告：对照 Excel 模板与 trace 使用情况")
    parser.add_argument("trace_file", help="trace JSON 文件路径")
    parser.add_argument("--excel", "-e", required=True, help="话术模板 Excel 文件路径")
    parser.add_argument(
        "--prob", "-p", default=None, help="概率矩阵 Excel 路径（可选，提供则作为模块全集权威来源）"
    )
    parser.add_argument(
        "--output-dir", "-o", default=None, help="报告输出目录（默认 trace 同级 analysis/）"
    )
    args = parser.parse_args()

    if not os.path.exists(args.trace_file):
        print(f"❌ trace 文件不存在: {args.trace_file}")
        sys.exit(1)
    if not os.path.exists(args.excel):
        print(f"❌ Excel 文件不存在: {args.excel}")
        sys.exit(1)
    if args.prob and not os.path.exists(args.prob):
        print(f"⚠️ prob 表不存在，将改用 Excel sheet 推断模块: {args.prob}")
        args.prob = None

    analyze_coverage(
        trace_path=args.trace_file,
        excel_path=args.excel,
        prob_path=args.prob,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
