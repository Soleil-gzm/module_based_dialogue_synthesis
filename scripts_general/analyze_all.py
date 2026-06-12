#!/usr/bin/env python3
"""
分析 trace 文件（支持命令行参数）：
- 施压话术位置分布（直方图）
- 再见触发位置分布（直方图）
- 触发原因分布（条形图）
- 对话轮数分布（直方图）
- 再见处理结果分布（条形图）

用法：
    python analyze_all.py --trace traces.json [--output_dir out_dir] [--format html|png]
    python analyze_all.py  # 使用硬编码路径（向后兼容）
"""

import argparse
import json
import os
import sys

# 添加项目根目录到 sys.path（方便直接运行）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.analyzer import DefaultAnalyzer, extract_timestamp_from_filename


def main():
    parser = argparse.ArgumentParser(description="分析 trace 文件并生成报告")
    parser.add_argument("--trace", type=str, help="trace JSON 文件路径")
    parser.add_argument("--output_dir", type=str, help="输出目录（默认自动生成）")
    parser.add_argument(
        "--format", choices=["html", "png"], default="html", help="图表格式"
    )
    parser.add_argument(
        "--pressure-config",
        type=str,
        help="JSON 格式的压力参数，例如 '{\"start_prob\":0.02}'",
    )
    args = parser.parse_args()

    # 确定 trace 路径
    if args.trace:
        trace_path = args.trace
    else:
        # 硬编码后备路径（可根据需要修改）
        trace_path = (
            "output/general_4000_42/intermediate/traces/traces_20260610_155816.json"
        )
        print(f"未指定 --trace，使用硬编码路径: {trace_path}")

    if not os.path.exists(trace_path):
        print(f"错误: trace 文件不存在: {trace_path}")
        sys.exit(1)

    # 确定输出目录
    if args.output_dir:
        output_dir = args.output_dir
    else:
        timestamp = extract_timestamp_from_filename(trace_path)
        trace_dir = os.path.dirname(trace_path)
        output_dir = os.path.join(trace_dir, "analysis", timestamp)

    # 解析压力参数
    pressure_config = None
    if args.pressure_config:
        try:
            pressure_config = json.loads(args.pressure_config)
        except json.JSONDecodeError:
            print("警告: pressure-config 格式错误，将忽略")

    # 创建分析器并执行
    analyzer = DefaultAnalyzer(format=args.format, pressure_config=pressure_config)
    try:
        analyzer.analyze(trace_path, output_dir)
    except Exception as e:
        print(f"分析失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
