#!/usr/bin/env python3
"""
综合分析 trace 文件：
- 施压话术在路径中的位置分布（直方图、模块频次）
- 对话停止原因分布（尤其是提前终止的路径长度分布）
输出结果放在与 trace 文件同名的文件夹下（根据文件名中的数量和日期时间）。
"""

import json
import os
from collections import Counter, defaultdict

# ========== 硬编码输入输出路径 ==========
INPUT_TRACE_FILE = "intermediate/traces/traces_40000_20260610_100849.json"   # 请修改为实际 trace 文件

# 自动生成输出目录：基于输入文件名（不含扩展名）
trace_basename = os.path.splitext(os.path.basename(INPUT_TRACE_FILE))[0]   # 例如 "traces_40000_20260610_100849"
OUTPUT_DIR = os.path.join("analysis", trace_basename)  # 例如 "analysis/traces_40000_20260610_100849"

OUTPUT_REPORT = os.path.join(OUTPUT_DIR, "full_analysis_report.txt")
OUTPUT_PRESSURE_HIST = os.path.join(OUTPUT_DIR, "pressure_position_histogram.png")
OUTPUT_STOP_HIST = os.path.join(OUTPUT_DIR, "early_stop_length_histogram.png")
OUTPUT_JSON = os.path.join(OUTPUT_DIR, "full_analysis.json")

# 尝试导入绘图库
try:
    import matplotlib.pyplot as plt
    HAS_PLT = True
except ImportError:
    HAS_PLT = False
    print("警告: matplotlib 未安装，将不生成图像。")

def load_traces(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Trace 文件不存在: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def analyze_pressure_positions(traces):
    """分析施压话术在路径中的位置分布"""
    summary = {
        "total_conversations": len(traces),
        "total_pressure_applied": 0,
        "pressure_by_module": defaultdict(int),
        "pressure_position_ratio": [],   # 归一化位置
        "pressure_absolute_index": [],   # 绝对索引
        "path_lengths": [],              # 每条对话路径长度
    }

    for trace in traces:
        path = trace.get("path", [])
        modules = trace.get("modules", [])
        path_len = len(path)
        summary["path_lengths"].append(path_len)

        for idx, module_trace in enumerate(modules):
            if idx >= path_len:
                break
            if module_trace.get("pressure_applied", False):
                summary["total_pressure_applied"] += 1
                module_name = module_trace.get("module")
                summary["pressure_by_module"][module_name] += 1
                if path_len > 1:
                    norm_pos = idx / (path_len - 1)
                else:
                    norm_pos = 0.0
                summary["pressure_position_ratio"].append(norm_pos)
                summary["pressure_absolute_index"].append(idx)

    summary["pressure_by_module"] = dict(summary["pressure_by_module"])
    return summary

def analyze_stop_reasons(traces):
    """分析对话停止原因"""
    stop_reason_counter = Counter()
    early_stop_lengths = []      # 提前终止（再见触发）的路径长度
    natural_end_lengths = []     # 自然结束的路径长度
    other_lengths = []           # 其他原因

    for trace in traces:
        path_len = len(trace.get("path", []))
        final_reason = trace.get("final_stop_reason", None)
        if final_reason is None:
            continue
        stop_reason_counter[final_reason] += 1
        if final_reason.startswith("goodbye"):
            early_stop_lengths.append(path_len)
        elif final_reason == "path_natural_end":
            natural_end_lengths.append(path_len)
        else:
            other_lengths.append(path_len)

    return {
        "stop_reason_counter": dict(stop_reason_counter),
        "early_stop_lengths": early_stop_lengths,
        "natural_end_lengths": natural_end_lengths,
        "other_lengths": other_lengths,
        "total_conversations": len(traces),
    }

def plot_histogram(data, title, xlabel, ylabel, output_file, bins=20):
    if not HAS_PLT or not data:
        return
    plt.figure(figsize=(10, 6))
    plt.hist(data, bins=bins, edgecolor='black', alpha=0.7)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.savefig(output_file, dpi=150)
    plt.close()
    print(f"直方图已保存至: {output_file}")

def plot_stop_length_histogram(lengths, output_file):
    if not lengths:
        return
    bins = range(min(lengths), max(lengths)+2)
    plot_histogram(lengths, "提前终止对话的路径长度分布", "路径长度（模块数）", "对话数量", output_file, bins=bins)

def plot_pressure_histogram(positions, output_file):
    if not positions:
        return
    plot_histogram(positions, "施压话术在路径中的位置分布", "归一化位置 (0=开头, 1=末尾)", "次数", output_file, bins=20)

def save_report(pressure_stats, stop_stats, output_file):
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("对话生成全面分析报告\n")
        f.write("=" * 60 + "\n\n")

        # 施压话术统计
        f.write("=== 施压话术统计 ===\n")
        f.write(f"总对话数: {pressure_stats['total_conversations']}\n")
        f.write(f"施压话术总次数: {pressure_stats['total_pressure_applied']}\n")
        if pressure_stats['pressure_position_ratio']:
            import numpy as np
            arr = np.array(pressure_stats['pressure_position_ratio'])
            f.write(f"施压位置均值: {np.mean(arr):.3f}\n")
            f.write(f"施压位置中位数: {np.median(arr):.3f}\n")
            f.write(f"施压位置标准差: {np.std(arr):.3f}\n")
        f.write("\n各模块施压次数:\n")
        for mod, cnt in sorted(pressure_stats['pressure_by_module'].items(), key=lambda x: x[1], reverse=True):
            f.write(f"  {mod}: {cnt}\n")
        f.write("\n")

        # 停止原因统计
        f.write("=== 对话停止原因统计 ===\n")
        f.write(f"总对话数: {stop_stats['total_conversations']}\n\n")
        f.write("停止原因分布:\n")
        for reason, cnt in sorted(stop_stats['stop_reason_counter'].items(), key=lambda x: x[1], reverse=True):
            f.write(f"  {reason}: {cnt}\n")
        f.write("\n")

        early = stop_stats['early_stop_lengths']
        if early:
            f.write(f"提前终止（再见触发）对话数: {len(early)}\n")
            f.write(f"  路径长度最小值: {min(early)}\n")
            f.write(f"  最大值: {max(early)}\n")
            f.write(f"  平均值: {sum(early)/len(early):.2f}\n")
        else:
            f.write("没有提前终止的对话。\n")
        natural = stop_stats['natural_end_lengths']
        if natural:
            f.write(f"\n自然结束对话数: {len(natural)}\n")
            f.write(f"  路径长度最小值: {min(natural)}\n")
            f.write(f"  最大值: {max(natural)}\n")
            f.write(f"  平均值: {sum(natural)/len(natural):.2f}\n")
    print(f"报告已保存至: {output_file}")

def save_json(pressure_stats, stop_stats, output_file):
    # 将 numpy 类型转换为 Python 原生类型
    data = {
        "pressure_statistics": {
            "total_conversations": pressure_stats['total_conversations'],
            "total_pressure_applied": pressure_stats['total_pressure_applied'],
            "pressure_position_mean": None,
            "pressure_position_median": None,
            "pressure_position_std": None,
            "pressure_by_module": pressure_stats['pressure_by_module'],
        },
        "stop_reason_statistics": {
            "total_conversations": stop_stats['total_conversations'],
            "stop_reason_counter": stop_stats['stop_reason_counter'],
            "early_stop_lengths": stop_stats['early_stop_lengths'],
            "natural_end_lengths": stop_stats['natural_end_lengths'],
        }
    }
    if pressure_stats['pressure_position_ratio']:
        import numpy as np
        arr = np.array(pressure_stats['pressure_position_ratio'])
        data['pressure_statistics']['pressure_position_mean'] = float(np.mean(arr))
        data['pressure_statistics']['pressure_position_median'] = float(np.median(arr))
        data['pressure_statistics']['pressure_position_std'] = float(np.std(arr))
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"JSON 分析结果已保存至: {output_file}")

def main():
    try:
        traces = load_traces(INPUT_TRACE_FILE)
        print(f"成功加载 {len(traces)} 条对话的 trace 数据")
        pressure_stats = analyze_pressure_positions(traces)
        stop_stats = analyze_stop_reasons(traces)

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        save_report(pressure_stats, stop_stats, OUTPUT_REPORT)
        save_json(pressure_stats, stop_stats, OUTPUT_JSON)

        if pressure_stats['pressure_position_ratio']:
            plot_pressure_histogram(pressure_stats['pressure_position_ratio'], OUTPUT_PRESSURE_HIST)
        else:
            print("没有施压话术记录，无法生成施压位置直方图。")
        if stop_stats['early_stop_lengths']:
            plot_stop_length_histogram(stop_stats['early_stop_lengths'], OUTPUT_STOP_HIST)
        else:
            print("没有提前终止的对话，无法生成停止长度直方图。")

    except Exception as e:
        print(f"错误: {e}")
        raise

if __name__ == "__main__":
    main()