#!/usr/bin/env python3
"""
分析 trace 文件（交互式版本）：
- 施压话术位置分布（直方图）
- 再见触发位置分布（直方图）
- 触发原因分布（条形图）
- 对话轮数分布（直方图）
- 再见处理结果分布（条形图）：触发/忽略/无再见
"""

import json
import os
import re
from collections import Counter, defaultdict

# ========== 硬编码输入输出 ==========
INPUT_TRACE_FILE = "output/general_v1_40000_42/intermediate/traces/traces_20260610_173304.json"  # 修改为实际文件
OUTPUT_DIR = "output/general_v1_40000_42/intermediate/analysis"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 输出文件（HTML 交互式）
PRESSURE_HIST_HTML = os.path.join(OUTPUT_DIR, "pressure_position_histogram.html")
GOODBYE_HIST_HTML = os.path.join(OUTPUT_DIR, "goodbye_position_histogram.html")
STOP_REASON_BAR_HTML = os.path.join(OUTPUT_DIR, "stop_reason_bar.html")
DIALOGUE_LENGTH_HIST = os.path.join(OUTPUT_DIR, "dialogue_length_histogram.html")
GOODBYE_HANDLING_BAR = os.path.join(OUTPUT_DIR, "goodbye_handling_bar.html")
REPORT_TXT = os.path.join(OUTPUT_DIR, "analysis_report.txt")

try:
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False
    print(
        "警告: Plotly 未安装，将生成静态 matplotlib 图表。如需交互式图表，请运行: pip install plotly"
    )


def load_traces(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def simplify_reason(reason):
    if not reason:
        return reason
    return re.sub(r"_\d+$", "", reason)


# def analyze(traces):
#     # 施压位置
#     pressure_positions = []
#     # 再见触发位置
#     goodbye_normalized = []
#     # 停止原因计数
#     stop_reason_counter = Counter()
#     # 对话轮数（每个对话的总 turn_count 之和）
#     dialogue_lengths = []
#     # 再见处理结果统计
#     goodbye_handling = {
#         "goodbye_triggered": 0,
#         "goodbye_ignored": 0,
#         "no_goodbye": 0,
#     }

#     for trace in traces:
#         path = trace.get("path", [])
#         modules = trace.get("modules", [])
#         final_reason = trace.get("final_stop_reason", None)
#         path_len = len(path)

#         # 停止原因
#         if final_reason:
#             simplified = simplify_reason(final_reason)
#             stop_reason_counter[simplified] += 1

#         # 对话轮数：累加每个模块的 turn_count
#         total_turns = sum(mod.get("turn_count", 0) for mod in modules)
#         dialogue_lengths.append(total_turns)

#         # 再见处理结果统计
#         has_triggered = any(mod.get("goodbye_triggered", False) for mod in modules)
#         has_ignored = any(mod.get("goodbye_ignored", False) for mod in modules)
#         is_stopped = final_reason and final_reason.startswith("goodbye")

#         if has_triggered:
#             if is_stopped:
#                 goodbye_handling["triggered_and_stopped"] += 1
#             else:
#                 goodbye_handling["triggered_but_not_stopped"] += 1
#         elif has_ignored:
#             goodbye_handling["ignored_no_trigger"] += 1
#         else:
#             goodbye_handling["no_goodbye"] += 1

#         # 再见触发位置（只针对 triggered 的对话）
#         if has_triggered:
#             # 找到第一个 goodbye_triggered=True 的模块索引
#             trigger_idx = None
#             for idx, mod in enumerate(modules):
#                 if mod.get("goodbye_triggered", False):
#                     trigger_idx = idx
#                     break
#             if trigger_idx is not None:
#                 if path_len > 1:
#                     goodbye_normalized.append(trigger_idx / (path_len - 1))
#                 else:
#                     goodbye_normalized.append(0.0)

#         # 施压位置
#         for idx, mod in enumerate(modules):
#             if mod.get("pressure_applied", False):
#                 if path_len > 1:
#                     pressure_positions.append(idx / (path_len - 1))
#                 else:
#                     pressure_positions.append(0.0)

#     return {
#         "pressure_positions": pressure_positions,
#         "goodbye_normalized": goodbye_normalized,
#         "stop_reason_counter": stop_reason_counter,
#         "dialogue_lengths": dialogue_lengths,
#         "goodbye_handling": goodbye_handling,
#         "total_conversations": len(traces),
#     }

def analyze(traces):
    # 施压位置（归一化）
    pressure_positions = []
    # 再见触发位置（归一化）
    goodbye_normalized = []
    # 停止原因计数（简化后）
    stop_reason_counter = Counter()
    # 每条对话的总轮数（所有模块的 turn_count 之和）
    dialogue_lengths = []
    # 再见处理统计
    goodbye_handling = {
        "goodbye_triggered": 0,   # 再见被触发且对话终止
        "goodbye_ignored": 0,     # 再见被忽略（未终止）
        "no_goodbye": 0,          # 从未出现再见
    }

    for trace in traces:
        path = trace.get("path", [])
        modules = trace.get("modules", [])
        final_reason = trace.get("final_stop_reason", None)
        path_len = len(path)

        # 停止原因（简化，去除数字后缀）
        if final_reason:
            simplified = simplify_reason(final_reason)
            stop_reason_counter[simplified] += 1

        # 对话轮数
        total_turns = sum(mod.get("turn_count", 0) for mod in modules)
        dialogue_lengths.append(total_turns)

        # 再见处理统计
        has_triggered = any(mod.get("goodbye_triggered", False) for mod in modules)
        has_ignored = any(mod.get("goodbye_ignored", False) for mod in modules)

        if has_triggered:
            goodbye_handling["goodbye_triggered"] += 1
        elif has_ignored:
            goodbye_handling["goodbye_ignored"] += 1
        else:
            goodbye_handling["no_goodbye"] += 1

        # 再见触发位置（仅针对 triggered 的对话）
        if has_triggered:
            # 找到第一个 goodbye_triggered=True 的模块索引
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

def create_histogram(data, title, xlabel, ylabel, output_html, nbins=20):
    if not data:
        print(f"警告: 没有数据可绘制 {title}")
        return
    fig = go.Figure(
        data=[go.Histogram(x=data, nbinsx=nbins, marker_color="#1f77b4", opacity=0.75)]
    )
    fig.update_layout(
        title=title,
        xaxis_title=xlabel,
        yaxis_title=ylabel,
        template="plotly_white",
        hovermode="closest",
        bargap=0.1,
    )
    fig.write_html(output_html)
    print(f"保存直方图: {output_html}")


def create_bar_chart(counter_or_dict, title, xlabel, ylabel, output_html):
    if not counter_or_dict:
        return
    if isinstance(counter_or_dict, dict):
        categories = list(counter_or_dict.keys())
        counts = list(counter_or_dict.values())
    else:
        categories = list(counter_or_dict.keys())
        counts = list(counter_or_dict.values())
    fig = go.Figure(
        data=[
            go.Bar(
                x=categories,
                y=counts,
                text=counts,
                textposition="auto",
                marker_color=px.colors.qualitative.Plotly[: len(categories)],
            )
        ]
    )
    fig.update_layout(
        title=title,
        xaxis_title=xlabel,
        yaxis_title=ylabel,
        template="plotly_white",
        xaxis_tickangle=-45,
    )
    fig.write_html(output_html)
    print(f"保存条形图: {output_html}")


def save_report(stats, output_file):
    import numpy as np

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=== Trace Analysis Report ===\n")
        f.write(f"Total conversations: {stats['total_conversations']}\n")
        f.write("\nStop reason distribution:\n")
        for reason, cnt in sorted(
            stats["stop_reason_counter"].items(), key=lambda x: x[1], reverse=True
        ):
            f.write(f"  {reason}: {cnt}\n")
        f.write("\nGoodbye handling:\n")
        for k, v in stats["goodbye_handling"].items():
            f.write(f"  {k}: {v}\n")
        if stats["pressure_positions"]:
            arr = np.array(stats["pressure_positions"])
            f.write(
                f"\nPressure position (normalized) mean: {np.mean(arr):.3f}, median: {np.median(arr):.3f}, std: {np.std(arr):.3f}\n"
            )
        if stats["goodbye_normalized"]:
            arr = np.array(stats["goodbye_normalized"])
            f.write(
                f"Goodbye trigger position (normalized) mean: {np.mean(arr):.3f}, median: {np.median(arr):.3f}, std: {np.std(arr):.3f}\n"
            )
        if stats["dialogue_lengths"]:
            arr = np.array(stats["dialogue_lengths"])
            f.write(
                f"Dialogue length (number of turns) mean: {np.mean(arr):.2f}, median: {np.median(arr):.2f}, min: {np.min(arr)}, max: {np.max(arr)}\n"
            )
    print(f"Report saved: {output_file}")


def main():
    print(f"Loading trace file: {INPUT_TRACE_FILE}")
    traces = load_traces(INPUT_TRACE_FILE)
    print(f"Loaded {len(traces)} conversations")
    stats = analyze(traces)

    if HAS_PLOTLY:
        create_histogram(
            stats["pressure_positions"],
            "Pressure Utterance Position Distribution",
            "Normalized Position (0=start, 1=end)",
            "Frequency",
            PRESSURE_HIST_HTML,
        )
        if stats["goodbye_normalized"]:
            create_histogram(
                stats["goodbye_normalized"],
                "Goodbye Trigger Position Distribution",
                "Normalized Position (0=start, 1=end)",
                "Frequency",
                GOODBYE_HIST_HTML,
            )
        else:
            print("No goodbye triggers found, skipping goodbye position histogram.")
        create_bar_chart(
            stats["stop_reason_counter"],
            "Stop Reason Distribution",
            "Stop Reason",
            "Number of Conversations",
            STOP_REASON_BAR_HTML,
        )
        create_histogram(
            stats["dialogue_lengths"],
            "Dialogue Length Distribution",
            "Number of Turns (user+assistant pairs)",
            "Frequency",
            DIALOGUE_LENGTH_HIST,
        )
        create_bar_chart(
            stats["goodbye_handling"],
            "Goodbye Handling Outcome",
            "Category",
            "Number of Conversations",
            GOODBYE_HANDLING_BAR,
        )
    else:
        # 回退到 matplotlib 静态图（略）
        print("Plotly not available, static charts generated (matplotlib).")
        import matplotlib.pyplot as plt
        import numpy as np

        if stats["pressure_positions"]:
            plt.figure()
            plt.hist(stats["pressure_positions"], bins=20, edgecolor="black", alpha=0.7)
            plt.xlabel("Normalized Position")
            plt.ylabel("Frequency")
            plt.title("Pressure Utterance Position Distribution")
            plt.grid(True)
            plt.savefig(PRESSURE_HIST_HTML.replace(".html", ".png"), dpi=150)
            plt.close()
        if stats["goodbye_normalized"]:
            plt.figure()
            plt.hist(stats["goodbye_normalized"], bins=20, edgecolor="black", alpha=0.7)
            plt.xlabel("Normalized Position")
            plt.ylabel("Frequency")
            plt.title("Goodbye Trigger Position Distribution")
            plt.grid(True)
            plt.savefig(GOODBYE_HIST_HTML.replace(".html", ".png"), dpi=150)
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
            plt.savefig(STOP_REASON_BAR_HTML.replace(".html", ".png"), dpi=150)
            plt.close()
        if stats["dialogue_lengths"]:
            plt.figure()
            plt.hist(stats["dialogue_lengths"], bins=20, edgecolor="black", alpha=0.7)
            plt.xlabel("Number of Turns")
            plt.ylabel("Frequency")
            plt.title("Dialogue Length Distribution")
            plt.grid(True)
            plt.savefig(DIALOGUE_LENGTH_HIST.replace(".html", ".png"), dpi=150)
            plt.close()
        if stats["goodbye_handling"]:
            categories = list(stats["goodbye_handling"].keys())
            counts = list(stats["goodbye_handling"].values())
            plt.figure(figsize=(8, 6))
            plt.bar(categories, counts, edgecolor="black", alpha=0.7)
            plt.ylabel("Number of Conversations")
            plt.title("Goodbye Handling Outcome")
            plt.tight_layout()
            plt.savefig(GOODBYE_HANDLING_BAR.replace(".html", ".png"), dpi=150)
            plt.close()

    save_report(stats, REPORT_TXT)
    print("Analysis complete.")


if __name__ == "__main__":
    main()
