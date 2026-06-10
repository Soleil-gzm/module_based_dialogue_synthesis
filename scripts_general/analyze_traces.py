#!/usr/bin/env python3
"""
分析 trace 记录中的路径及施压话术添加位置，并绘制位置分布直方图。
"""

import json
import os
from collections import defaultdict, Counter
import sys
import numpy as np

# ========== 硬编码输入输出路径 ==========
INPUT_TRACE_FILE = "intermediate/traces/traces_40000_20260610_143507.json"   # 请根据实际文件名修改
OUTPUT_ANALYSIS_FILE = "intermediate/analysis/px_40000_20260610_143507/pressure_positions.json"
OUTPUT_HISTOGRAM_FILE = "intermediate/analysis/px_40000_20260610_143507/pressure_position_histogram.png"

# 是否尝试生成图像
try:
    import matplotlib.pyplot as plt
    HAS_PLT = True
except ImportError:
    HAS_PLT = False
    print("警告: matplotlib 未安装，将不生成图像。")

def load_traces(file_path: str):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Trace 文件不存在: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def analyze_traces(traces):
    summary = {
        "total_conversations": len(traces),
        "total_pressure_applied": 0,
        "pressure_by_module": defaultdict(int),
        "pressure_position_ratio": [],   # 每条施压的归一化位置 (0~1)
        "pressure_absolute_index": [],   # 每条施压的绝对索引
        "path_lengths": [],              # 每条对话的路径长度
    }

    conversations = []

    for trace in traces:
        path = trace.get("path", [])
        modules = trace.get("modules", [])
        path_len = len(path)
        summary["path_lengths"].append(path_len)
        pressure_positions = []

        for idx, module_trace in enumerate(modules):
            if idx >= path_len:
                break
            module_name = module_trace.get("module")
            if module_trace.get("pressure_applied", False):
                pressure_positions.append({
                    "index": idx,
                    "module": module_name,
                    "repeat": module_trace.get("repeat", 0),
                    "segment_length": module_trace.get("pressure_segment_length", 0)
                })
                summary["total_pressure_applied"] += 1
                summary["pressure_by_module"][module_name] += 1
                # 记录归一化位置 (0~1)
                if path_len > 1:
                    norm_pos = idx / (path_len - 1)
                else:
                    norm_pos = 0.0
                summary["pressure_position_ratio"].append(norm_pos)
                summary["pressure_absolute_index"].append(idx)

        conversations.append({
            "path": path,
            "pressure_positions": pressure_positions
        })

    summary["pressure_by_module"] = dict(summary["pressure_by_module"])
    return {
        "summary": summary,
        "conversations": conversations
    }

def plot_histogram(position_ratios, output_file):
    if not HAS_PLT or not position_ratios:
        return
    plt.figure(figsize=(10, 6))
    plt.hist(position_ratios, bins=20, edgecolor='black', alpha=0.7)
    plt.xlabel("Normalized Position in Path (0=start, 1=end)")
    plt.ylabel("Frequency")
    plt.title("Distribution of Pressure Utterance Positions")
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.savefig(output_file, dpi=150)
    plt.close()
    print(f"直方图已保存至: {output_file}")

def print_text_histogram(position_ratios, bins=10):
    if not position_ratios:
        print("没有施压话术数据，无法生成直方图。")
        return
    counts, bin_edges = np.histogram(position_ratios, bins=bins)
    print("\n=== 施压话术位置分布（文本直方图）===")
    for i in range(len(counts)):
        low = bin_edges[i]
        high = bin_edges[i+1]
        bar = '#' * int(counts[i] / max(counts) * 50) if max(counts) > 0 else ''
        print(f"{low:.2f} - {high:.2f}: {counts[i]:4d} {bar}")
    # 打印统计量
    import numpy as np
    arr = np.array(position_ratios)
    print(f"\n统计量: 均值={np.mean(arr):.3f}, 中位数={np.median(arr):.3f}, 标准差={np.std(arr):.3f}")
    print(f"样本数: {len(arr)}")

def main():
    try:
        traces = load_traces(INPUT_TRACE_FILE)
        print(f"成功加载 {len(traces)} 条对话的 trace 数据")
        analysis = analyze_traces(traces)
        summary = analysis["summary"]
        
        # 保存 JSON
        os.makedirs(os.path.dirname(OUTPUT_ANALYSIS_FILE), exist_ok=True)
        with open(OUTPUT_ANALYSIS_FILE, "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
        print(f"分析结果已保存至: {OUTPUT_ANALYSIS_FILE}")
        
        # 打印基本统计
        print(f"总对话数: {summary['total_conversations']}")
        print(f"总共添加施压话术次数: {summary['total_pressure_applied']}")
        print("各模块施压频次:")
        for mod, cnt in sorted(summary["pressure_by_module"].items(), key=lambda x: x[1], reverse=True):
            print(f"  {mod}: {cnt}")
        
        # 位置分布
        position_ratios = summary["pressure_position_ratio"]
        if position_ratios:
            print(f"\n施压话术位置分布样本数: {len(position_ratios)}")
            # 尝试使用 numpy 快速统计
            try:
                import numpy as np
                print_text_histogram(position_ratios)
                plot_histogram(position_ratios, OUTPUT_HISTOGRAM_FILE)
            except ImportError:
                print("numpy 未安装，无法生成直方图。")
        else:
            print("没有施压话术记录，无法分析位置分布。")
            
    except Exception as e:
        print(f"错误: {e}")
        raise

if __name__ == "__main__":
    main()