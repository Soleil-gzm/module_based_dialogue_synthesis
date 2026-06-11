#!/usr/bin/env python3
"""
分析 trace 文件（交互式版本）：
- 施压话术位置分布（直方图）
- 再见触发位置分布（直方图）
- 触发原因分布（条形图）
- 对话轮数分布（直方图）
- 再见处理结果分布（条形图）：触发/忽略/无再见

用法：
    python analyze_all.py --trace traces.json [--output_dir out_dir]
    python analyze_all.py  # 使用脚本内硬编码路径（向后兼容）
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Dict, List, Any

# ---------- 导入绘图库 ----------
try:
    import plotly.express as px
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False
    import matplotlib.pyplot as plt
    import numpy as np

# ---------- 路径处理 ----------
def extract_timestamp_from_filename(filepath: str) -> str:
    """从文件名中提取时间戳，如 traces_20260611_142040.json -> 20260611_142040"""
    basename = os.path.basename(filepath)
    match = re.search(r'traces_(\d{8}_\d{6})\.json', basename)
    if match:
        return match.group(1)
    # 回退：使用文件修改时间
    import time
    return time.strftime("%Y%m%d_%H%M%S", time.localtime(os.path.getmtime(filepath)))


def simplify_reason(reason: str) -> str:
    """简化停止原因，去掉末尾的数字ID"""
    if not reason:
        return reason
    return re.sub(r'_\d+$', '', reason)


def analyze(traces: List[Dict]) -> Dict:
    """核心分析逻辑，返回统计数据字典"""
    pressure_positions = []
    goodbye_normalized = []
    stop_reason_counter = Counter()
    dialogue_lengths = []
    goodbye_handling = {
        "triggered_and_stopped": 0,
        "triggered_but_not_stopped": 0,
        "ignored_no_trigger": 0,
        "no_goodbye": 0,
    }

    for trace in traces:
        path = trace.get("path", [])
        modules = trace.get("modules", [])
        final_reason = trace.get("final_stop_reason", None)
        path_len = len(path)

        # 停止原因
        if final_reason:
            simplified = simplify_reason(final_reason)
            stop_reason_counter[simplified] += 1

        # 对话轮数
        total_turns = sum(mod.get("turn_count", 0) for mod in modules)
        dialogue_lengths.append(total_turns)

        # 再见处理结果
        has_triggered = any(mod.get("goodbye_triggered", False) for mod in modules)
        has_ignored = any(mod.get("goodbye_ignored", False) for mod in modules)
        is_stopped = final_reason and final_reason.startswith("goodbye")

        if has_triggered:
            if is_stopped:
                goodbye_handling["triggered_and_stopped"] += 1
            else:
                goodbye_handling["triggered_but_not_stopped"] += 1
        elif has_ignored:
            goodbye_handling["ignored_no_trigger"] += 1
        else:
            goodbye_handling["no_goodbye"] += 1

        # 再见触发位置（归一化）
        if has_triggered:
            trigger_idx = None
            for idx, mod in enumerate(modules):
                if mod.get("goodbye_triggered", False):
                    trigger_idx = idx
                    break
            if trigger_idx is not None:
                if path_len > 1:
                    goodbye_normalized.append(trigger_idx / (path_len - 1))
                else:
                    goodbye_normalized.append(0.0)

        # 施压位置
        for idx, mod in enumerate(modules):
            if mod.get("pressure_applied", False):
                if path_len > 1:
                    pressure_positions.append(idx / (path_len - 1))
                else:
                    pressure_positions.append(0.0)

    return {
        "pressure_positions": pressure_positions,
        "goodbye_normalized": goodbye_normalized,
        "stop_reason_counter": stop_reason_counter,
        "dialogue_lengths": dialogue_lengths,
        "goodbye_handling": goodbye_handling,
        "total_conversations": len(traces),
    }


def save_report(stats: Dict, output_file: str):
    """保存文本报告"""
    import numpy as np
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=== Trace Analysis Report ===\n")
        f.write(f"Total conversations: {stats['total_conversations']}\n")
        f.write("\nStop reason distribution:\n")
        for reason, cnt in sorted(stats["stop_reason_counter"].items(), key=lambda x: x[1], reverse=True):
            f.write(f"  {reason}: {cnt}\n")
        f.write("\nGoodbye handling:\n")
        for k, v in stats["goodbye_handling"].items():
            f.write(f"  {k}: {v}\n")
        if stats["pressure_positions"]:
            arr = np.array(stats["pressure_positions"])
            f.write(f"\nPressure position (normalized) mean: {np.mean(arr):.3f}, median: {np.median(arr):.3f}, std: {np.std(arr):.3f}\n")
        if stats["goodbye_normalized"]:
            arr = np.array(stats["goodbye_normalized"])
            f.write(f"Goodbye trigger position (normalized) mean: {np.mean(arr):.3f}, median: {np.median(arr):.3f}, std: {np.std(arr):.3f}\n")
        if stats["dialogue_lengths"]:
            arr = np.array(stats["dialogue_lengths"])
            f.write(f"Dialogue length (number of turns) mean: {np.mean(arr):.2f}, median: {np.median(arr):.2f}, min: {np.min(arr)}, max: {np.max(arr)}\n")


def generate_html_charts(stats: Dict, output_dir: str):
    """生成交互式 HTML 图表（使用 plotly）"""
    if not HAS_PLOTLY:
        print("Plotly 未安装，无法生成 HTML 图表，请使用 `pip install plotly` 或指定其他格式")
        return

    # 施压位置直方图
    if stats["pressure_positions"]:
        fig = go.Figure(data=[go.Histogram(x=stats["pressure_positions"], nbinsx=20, marker_color="#1f77b4", opacity=0.75)])
        fig.update_layout(title="Pressure Utterance Position Distribution", xaxis_title="Normalized Position (0=start, 1=end)", yaxis_title="Frequency", template="plotly_white")
        fig.write_html(os.path.join(output_dir, "pressure_position_histogram.html"))

    # 再见触发位置直方图
    if stats["goodbye_normalized"]:
        fig = go.Figure(data=[go.Histogram(x=stats["goodbye_normalized"], nbinsx=20, marker_color="#ff7f0e", opacity=0.75)])
        fig.update_layout(title="Goodbye Trigger Position Distribution", xaxis_title="Normalized Position", yaxis_title="Frequency", template="plotly_white")
        fig.write_html(os.path.join(output_dir, "goodbye_position_histogram.html"))

    # 停止原因条形图
    if stats["stop_reason_counter"]:
        categories = list(stats["stop_reason_counter"].keys())
        counts = list(stats["stop_reason_counter"].values())
        fig = go.Figure(data=[go.Bar(x=categories, y=counts, text=counts, textposition="auto", marker_color=px.colors.qualitative.Plotly[:len(categories)])])
        fig.update_layout(title="Stop Reason Distribution", xaxis_title="Stop Reason", yaxis_title="Number of Conversations", template="plotly_white", xaxis_tickangle=-45)
        fig.write_html(os.path.join(output_dir, "stop_reason_bar.html"))

    # 对话轮数直方图
    if stats["dialogue_lengths"]:
        fig = go.Figure(data=[go.Histogram(x=stats["dialogue_lengths"], nbinsx=20, marker_color="#2ca02c", opacity=0.75)])
        fig.update_layout(title="Dialogue Length Distribution", xaxis_title="Number of Turns", yaxis_title="Frequency", template="plotly_white")
        fig.write_html(os.path.join(output_dir, "dialogue_length_histogram.html"))

    # 再见处理结果条形图
    if stats["goodbye_handling"]:
        categories = list(stats["goodbye_handling"].keys())
        counts = list(stats["goodbye_handling"].values())
        fig = go.Figure(data=[go.Bar(x=categories, y=counts, text=counts, textposition="auto", marker_color=px.colors.qualitative.Set2[:len(categories)])])
        fig.update_layout(title="Goodbye Handling Outcome", xaxis_title="Category", yaxis_title="Number of Conversations", template="plotly_white")
        fig.write_html(os.path.join(output_dir, "goodbye_handling_bar.html"))


def generate_png_charts(stats: Dict, output_dir: str):
    """生成 PNG 静态图表（matplotlib 回退）"""
    import matplotlib.pyplot as plt
    import numpy as np

    if stats["pressure_positions"]:
        plt.figure()
        plt.hist(stats["pressure_positions"], bins=20, edgecolor="black", alpha=0.7)
        plt.xlabel("Normalized Position")
        plt.ylabel("Frequency")
        plt.title("Pressure Utterance Position Distribution")
        plt.grid(True)
        plt.savefig(os.path.join(output_dir, "pressure_position_histogram.png"), dpi=150)
        plt.close()

    if stats["goodbye_normalized"]:
        plt.figure()
        plt.hist(stats["goodbye_normalized"], bins=20, edgecolor="black", alpha=0.7)
        plt.xlabel("Normalized Position")
        plt.ylabel("Frequency")
        plt.title("Goodbye Trigger Position Distribution")
        plt.grid(True)
        plt.savefig(os.path.join(output_dir, "goodbye_position_histogram.png"), dpi=150)
        plt.close()

    if stats["stop_reason_counter"]:
        categories = list(stats["stop_reason_counter"].keys())
        counts = list(stats["stop_reason_counter"].values())
        plt.figure(figsize=(10, 6))
        plt.bar(categories, counts, edgecolor="black", alpha=0.7)
        plt.xticks(rotation=45, ha="right")
        plt.ylabel("Number of Conversations")
        plt.title("Stop Reason Distribution")
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "stop_reason_bar.png"), dpi=150)
        plt.close()

    if stats["dialogue_lengths"]:
        plt.figure()
        plt.hist(stats["dialogue_lengths"], bins=20, edgecolor="black", alpha=0.7)
        plt.xlabel("Number of Turns")
        plt.ylabel("Frequency")
        plt.title("Dialogue Length Distribution")
        plt.grid(True)
        plt.savefig(os.path.join(output_dir, "dialogue_length_histogram.png"), dpi=150)
        plt.close()

    if stats["goodbye_handling"]:
        categories = list(stats["goodbye_handling"].keys())
        counts = list(stats["goodbye_handling"].values())
        plt.figure(figsize=(8, 6))
        plt.bar(categories, counts, edgecolor="black", alpha=0.7)
        plt.ylabel("Number of Conversations")
        plt.title("Goodbye Handling Outcome")
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "goodbye_handling_bar.png"), dpi=150)
        plt.close()


def analyze_traces_file(trace_path: str, output_dir: str, plot_format: str = "html"):
    """
    供外部调用的主函数：分析 trace 文件并生成报告
    :param trace_path: trace JSON 文件路径
    :param output_dir: 输出目录（若不存在则创建）
    :param plot_format: "html" 或 "png"
    """
    if not os.path.exists(trace_path):
        raise FileNotFoundError(f"Trace file not found: {trace_path}")

    os.makedirs(output_dir, exist_ok=True)

    # 加载 traces
    with open(trace_path, "r", encoding="utf-8") as f:
        traces = json.load(f)

    print(f"Loaded {len(traces)} conversations from {trace_path}")

    # 分析
    stats = analyze(traces)

    # 保存文本报告
    report_file = os.path.join(output_dir, "analysis_report.txt")
    save_report(stats, report_file)
    print(f"Report saved: {report_file}")

    # 生成图表
    if plot_format == "html" and HAS_PLOTLY:
        generate_html_charts(stats, output_dir)
        print(f"HTML charts saved in {output_dir}")
    elif plot_format == "png":
        generate_png_charts(stats, output_dir)
        print(f"PNG charts saved in {output_dir}")
    else:
        print(f"Plot format '{plot_format}' not supported or plotly missing, skipping charts.")


def main():
    parser = argparse.ArgumentParser(description="Analyze trace JSON and generate reports")
    parser.add_argument("--trace", type=str, help="Path to trace JSON file")
    parser.add_argument("--output_dir", type=str, help="Output directory (default: auto-generated from trace path)")
    parser.add_argument("--format", choices=["html", "png"], default="html", help="Chart format (html or png)")
    args = parser.parse_args()

    # 确定 trace 文件路径
    if args.trace:
        trace_path = args.trace
    else:
        # 向后兼容的硬编码路径（可根据需要修改）
        trace_path = "output/general_4000_42/intermediate/traces/traces_20260610_155816.json"
        print(f"未指定 --trace，使用硬编码路径: {trace_path}")

    if not os.path.exists(trace_path):
        print(f"错误: trace 文件不存在: {trace_path}")
        sys.exit(1)

    # 确定输出目录
    if args.output_dir:
        output_dir = args.output_dir
    else:
        # 自动生成：trace 文件同级目录/analysis/时间戳/
        timestamp = extract_timestamp_from_filename(trace_path)
        trace_dir = os.path.dirname(trace_path)
        output_dir = os.path.join(trace_dir, "analysis", timestamp)

    try:
        analyze_traces_file(trace_path, output_dir, args.format)
    except Exception as e:
        print(f"分析失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()