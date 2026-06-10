#!/usr/bin/env python3
"""
分析 trace 文件（交互式版本）：
- 施压话术位置分布（直方图）
- 再见触发位置分布（直方图）
- 触发原因分布（条形图，交互式）
"""

import json
import os
import re
from collections import Counter

# ========== 硬编码输入输出 ==========
INPUT_TRACE_FILE = "output/general_100_42_100_42/intermediate/traces/traces_20260610_150457.json"  # 修改为实际文件
OUTPUT_DIR = "output/general_100_42_100_42/intermediate/analysis"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 输出文件（HTML 交互式）
PRESSURE_HIST_HTML = os.path.join(OUTPUT_DIR, "pressure_position_histogram.html")
GOODBYE_HIST_HTML = os.path.join(OUTPUT_DIR, "goodbye_position_histogram.html")
STOP_REASON_BAR_HTML = os.path.join(OUTPUT_DIR, "stop_reason_bar.html")
REPORT_TXT = os.path.join(OUTPUT_DIR, "analysis_report.txt")

# 尝试导入 plotly
try:
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False
    print("警告: Plotly 未安装，将生成静态 matplotlib 图表。如需交互式图表，请运行: pip install plotly")


def load_traces(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def simplify_reason(reason):
    """去除停止原因末尾的数字，例如 'goodbye_in_current_12' -> 'goodbye_in_current'"""
    if not reason:
        return reason
    # 匹配末尾的 _数字
    return re.sub(r'_\d+$', '', reason)


def analyze(traces):
    pressure_positions = []        # 归一化位置
    goodbye_normalized = []
    stop_reason_counter = Counter()
    goodbye_conversations = 0

    for trace in traces:
        path = trace.get("path", [])
        modules = trace.get("modules", [])
        final_reason = trace.get("final_stop_reason", None)
        path_len = len(path)

        if final_reason:
            simplified = simplify_reason(final_reason)
            stop_reason_counter[simplified] += 1
            if final_reason.startswith("goodbye"):
                goodbye_conversations += 1
                # 找到再见触发的模块索引（第一个 goodbye_triggered=True 的模块）
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
        "total_conversations": len(traces),
        "goodbye_conversations": goodbye_conversations,
    }


def create_histogram(data, title, xlabel, ylabel, output_html):
    """创建交互式直方图（使用单一高对比色 + 透明度）"""
    if not data:
        print(f"警告: 没有数据可绘制 {title}")
        return
    fig = go.Figure(data=[go.Histogram(x=data, nbinsx=20, 
                                       marker_color='#1f77b4', 
                                       opacity=0.75,
                                       name='Count')])
    fig.update_layout(
        title=title,
        xaxis_title=xlabel,
        yaxis_title=ylabel,
        template='plotly_white',
        hovermode='closest',
        bargap=0.1
    )
    fig.write_html(output_html)
    print(f"保存直方图: {output_html}")

# 使用单一颜色
def create_bar_chart(counter, title, xlabel, ylabel, output_html):
    """创建条形图（每个柱子不同颜色）"""
    if not counter:
        return
    categories = list(counter.keys())
    counts = list(counter.values())
    # 使用 Plotly 的默认颜色序列（自动分配不同颜色）
    fig = go.Figure(data=[go.Bar(x=categories, y=counts, 
                                 marker_color='coral',   # 也可用其他颜色，如需不同颜色可注释掉此行
                                 # 如果要每个柱子不同颜色，可以使用：
                                #  marker_color=px.colors.qualitative.Plotly[:len(categories)]
                                 text=counts, textposition='auto')])
    fig.update_layout(
        title=title,
        xaxis_title=xlabel,
        yaxis_title=ylabel,
        template='plotly_white',
        xaxis_tickangle=-45
    )
    fig.write_html(output_html)
    print(f"保存条形图: {output_html}")

# 使用不同颜色
# def create_bar_chart(counter, title, xlabel, ylabel, output_html):
#     if not counter:
#         return
#     categories = list(counter.keys())
#     counts = list(counter.values())
#     fig = go.Figure(data=[go.Bar(x=categories, y=counts, 
#                                  marker_color=px.colors.qualitative.Plotly[:len(categories)],
#                                  text=counts, textposition='auto')])
#     fig.update_layout(
#         title=title,
#         xaxis_title=xlabel,
#         yaxis_title=ylabel,
#         template='plotly_white',
#         xaxis_tickangle=-45
#     )
#     fig.write_html(output_html)
#     print(f"保存条形图: {output_html}")

def save_report(stats, output_file):
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=== Trace Analysis Report ===\n")
        f.write(f"Total conversations: {stats['total_conversations']}\n")
        f.write(f"Early stopped (goodbye) conversations: {stats['goodbye_conversations']}\n\n")
        f.write("Stop reason distribution:\n")
        for reason, cnt in sorted(stats['stop_reason_counter'].items(), key=lambda x: x[1], reverse=True):
            f.write(f"  {reason}: {cnt}\n")
        f.write("\n")
        if stats['pressure_positions']:
            import numpy as np
            arr = np.array(stats['pressure_positions'])
            f.write("Pressure position statistics (normalized):\n")
            f.write(f"  Mean: {np.mean(arr):.3f}\n")
            f.write(f"  Median: {np.median(arr):.3f}\n")
            f.write(f"  Std: {np.std(arr):.3f}\n")
        if stats['goodbye_normalized']:
            import numpy as np
            arr = np.array(stats['goodbye_normalized'])
            f.write("\nGoodbye position statistics (normalized):\n")
            f.write(f"  Mean: {np.mean(arr):.3f}\n")
            f.write(f"  Median: {np.median(arr):.3f}\n")
            f.write(f"  Std: {np.std(arr):.3f}\n")
    print(f"Report saved: {output_file}")


def main():
    print(f"Loading trace file: {INPUT_TRACE_FILE}")
    traces = load_traces(INPUT_TRACE_FILE)
    print(f"Loaded {len(traces)} conversations")
    stats = analyze(traces)

    # 创建交互式图表（使用 Plotly）
    if HAS_PLOTLY:
        create_histogram(
            stats['pressure_positions'],
            "Pressure Utterance Position Distribution",
            "Normalized Position (0=start, 1=end)",
            "Frequency",
            PRESSURE_HIST_HTML
        )
        if stats['goodbye_normalized']:
            create_histogram(
                stats['goodbye_normalized'],
                "Goodbye Trigger Position Distribution",
                "Normalized Position (0=start, 1=end)",
                "Frequency",
                GOODBYE_HIST_HTML
            )
        else:
            print("No goodbye triggers found, skipping goodbye position histogram.")
        create_bar_chart(
            stats['stop_reason_counter'],
            "Stop Reason Distribution",
            "Stop Reason",
            "Number of Conversations",
            STOP_REASON_BAR_HTML
        )
    else:
        # 回退到 matplotlib 静态图
        print("Plotly not available, using matplotlib static charts.")
        import matplotlib.pyplot as plt
        import numpy as np
        if stats['pressure_positions']:
            plt.figure()
            plt.hist(stats['pressure_positions'], bins=20, edgecolor='black', alpha=0.7)
            plt.xlabel("Normalized Position")
            plt.ylabel("Frequency")
            plt.title("Pressure Utterance Position Distribution")
            plt.grid(True, linestyle='--', alpha=0.6)
            plt.savefig(PRESSURE_HIST_HTML.replace('.html', '.png'), dpi=150)
            plt.close()
        if stats['goodbye_normalized']:
            plt.figure()
            plt.hist(stats['goodbye_normalized'], bins=20, edgecolor='black', alpha=0.7)
            plt.xlabel("Normalized Position")
            plt.ylabel("Frequency")
            plt.title("Goodbye Trigger Position Distribution")
            plt.grid(True, linestyle='--', alpha=0.6)
            plt.savefig(GOODBYE_HIST_HTML.replace('.html', '.png'), dpi=150)
            plt.close()
        if stats['stop_reason_counter']:
            categories = list(stats['stop_reason_counter'].keys())
            counts = list(stats['stop_reason_counter'].values())
            plt.figure(figsize=(10,6))
            plt.bar(categories, counts, edgecolor='black', alpha=0.7)
            plt.xticks(rotation=45, ha='right')
            plt.ylabel("Number of Conversations")
            plt.title("Stop Reason Distribution")
            plt.tight_layout()
            plt.savefig(STOP_REASON_BAR_HTML.replace('.html', '.png'), dpi=150)
            plt.close()

    save_report(stats, REPORT_TXT)
    print("Analysis complete.")


if __name__ == "__main__":
    main()