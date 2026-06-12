"""
分析器模块：对 trace 文件进行分析并生成报告。
提供抽象基类和默认实现，支持可扩展的分析方式。
"""

import json
import os
import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import Dict, List, Optional

import numpy as np

# 绘图库（可选）
try:
    import plotly.express as px
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False
    import matplotlib.pyplot as plt


def extract_timestamp_from_filename(filepath: str) -> str:
    """从文件名提取时间戳，如 traces_20260611_142040.json -> 20260611_142040"""
    basename = os.path.basename(filepath)
    match = re.search(r"traces_(\d{8}_\d{6})\.json", basename)
    if match:
        return match.group(1)
    import time
    return time.strftime("%Y%m%d_%H%M%S", time.localtime(os.path.getmtime(filepath)))


def simplify_reason(reason: str) -> str:
    """简化停止原因，去掉末尾的UID"""
    if not reason:
        return reason
    return re.sub(r"_\d+$", "", reason)


def analyze_traces_data(traces: List[Dict]) -> Dict:
    """核心统计逻辑，返回统计数据字典"""
    pressure_positions = []
    goodbye_normalized = []
    stop_reason_counter = Counter()
    dialogue_lengths = []
    goodbye_handling = {
        "triggered_and_stopped": 0,
        "triggered_but_not_stopped": 0,
        "natural_end": 0,
    }

    for trace in traces:
        path = trace.get("path", [])
        modules = trace.get("modules", [])
        final_reason = trace.get("final_stop_reason", None)
        path_len = len(path)

        if final_reason:
            simplified = simplify_reason(final_reason)
            stop_reason_counter[simplified] += 1

        total_turns = sum(mod.get("turn_count", 0) for mod in modules)
        dialogue_lengths.append(total_turns)

        has_triggered = any(mod.get("goodbye_triggered", False) for mod in modules)
        is_stopped = final_reason and final_reason.startswith("goodbye")

        if has_triggered:
            if is_stopped:
                goodbye_handling["triggered_and_stopped"] += 1
            else:
                goodbye_handling["triggered_but_not_stopped"] += 1
        else:
            goodbye_handling["natural_end"] += 1

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


class Analyzer(ABC):
    """分析器抽象基类"""

    @abstractmethod
    def analyze(self, trace_path: str, output_dir: str, **kwargs) -> None:
        """分析 trace 文件并生成报告"""
        pass


class DefaultAnalyzer(Analyzer):
    """默认分析器：生成 HTML/PNG 图表和文本报告"""

    def __init__(self, format: str = "html", pressure_config: Optional[Dict] = None):
        self.format = format          # "html" 或 "png"
        self.pressure_config = pressure_config or {}

    def _save_text_report(self, stats: Dict, output_file: str):
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("=== Trace Analysis Report ===\n")
            f.write(f"Total conversations: {stats['total_conversations']}\n")
            f.write("\nStop reason distribution:\n")
            for reason, cnt in sorted(stats["stop_reason_counter"].items(), key=lambda x: x[1], reverse=True):
                f.write(f"  {reason}: {cnt}\n")
            f.write("\nGoodbye handling:\n")
            f.write(f"  triggered_and_stopped (直接触发再见并停止): {stats['goodbye_handling']['triggered_and_stopped']}\n")
            f.write(f"  triggered_but_not_stopped (触发再见但忽略): {stats['goodbye_handling']['triggered_but_not_stopped']}\n")
            f.write(f"  natural_end (自然结束，未触发再见): {stats['goodbye_handling']['natural_end']}\n")
            if stats["pressure_positions"]:
                arr = np.array(stats["pressure_positions"])
                f.write(f"\nPressure position (normalized) mean: {np.mean(arr):.3f}, median: {np.median(arr):.3f}, std: {np.std(arr):.3f}\n")
            if stats["goodbye_normalized"]:
                arr = np.array(stats["goodbye_normalized"])
                f.write(f"Goodbye trigger position (normalized) mean: {np.mean(arr):.3f}, median: {np.median(arr):.3f}, std: {np.std(arr):.3f}\n")
            if stats["dialogue_lengths"]:
                arr = np.array(stats["dialogue_lengths"])
                f.write(f"Dialogue length (number of turns) mean: {np.mean(arr):.2f}, median: {np.median(arr):.2f}, min: {np.min(arr)}, max: {np.max(arr)}\n")
        print(f"Report saved: {output_file}")

    def _create_histogram(self, data, title, xlabel, ylabel, output_html, nbins=20):
        if not data:
            print(f"警告: 没有数据可绘制 {title}")
            return
        fig = go.Figure(data=[go.Histogram(x=data, nbinsx=nbins, marker_color="#1f77b4", opacity=0.75)])
        fig.update_layout(title=title, xaxis_title=xlabel, yaxis_title=ylabel, template="plotly_white", bargap=0.1)
        fig.write_html(output_html)
        print(f"保存直方图: {output_html}")

    def _create_bar_chart(self, counter_or_dict, title, xlabel, ylabel, output_html):
        if not counter_or_dict:
            return
        if isinstance(counter_or_dict, dict):
            categories = list(counter_or_dict.keys())
            counts = list(counter_or_dict.values())
        else:
            categories = list(counter_or_dict.keys())
            counts = list(counter_or_dict.values())
        fig = go.Figure(data=[go.Bar(x=categories, y=counts, text=counts, textposition="auto",
                                     marker_color=px.colors.qualitative.Plotly[:len(categories)])])
        fig.update_layout(title=title, xaxis_title=xlabel, yaxis_title=ylabel, template="plotly_white", xaxis_tickangle=-45)
        fig.write_html(output_html)
        print(f"保存条形图: {output_html}")

    def _generate_html_charts(self, stats: Dict, output_dir: str):
        if not HAS_PLOTLY:
            print("Plotly 未安装，无法生成 HTML 图表")
            return

        # 构建副标题（压力参数）
        subtitle = ""
        if self.pressure_config:
            subtitle = (f"<br><sub>动态施压参数: start={self.pressure_config.get('start_prob')}, "
                        f"end={self.pressure_config.get('end_prob')}, exponent={self.pressure_config.get('exponent')}, "
                        f"max_total={self.pressure_config.get('max_total')}, mode={self.pressure_config.get('mode')}</sub>")

        # 施压位置
        self._create_histogram(
            stats["pressure_positions"],
            f"Pressure Utterance Position Distribution{subtitle}",
            "Normalized Position (0=start, 1=end)", "Frequency",
            os.path.join(output_dir, "pressure_position_histogram.html")
        )
        # 再见触发位置
        if stats["goodbye_normalized"]:
            self._create_histogram(
                stats["goodbye_normalized"],
                f"Goodbye Trigger Position Distribution{subtitle}",
                "Normalized Position (0=start, 1=end)", "Frequency",
                os.path.join(output_dir, "goodbye_position_histogram.html")
            )
        else:
            print("No goodbye triggers found, skipping goodbye position histogram.")
        # 停止原因
        self._create_bar_chart(
            stats["stop_reason_counter"],
            "Stop Reason Distribution", "Stop Reason", "Number of Conversations",
            os.path.join(output_dir, "stop_reason_bar.html")
        )
        # 对话轮数
        self._create_histogram(
            stats["dialogue_lengths"],
            "Dialogue Length Distribution", "Number of Turns (user+assistant pairs)", "Frequency",
            os.path.join(output_dir, "dialogue_length_histogram.html")
        )
        # 再见处理结果
        self._create_bar_chart(
            stats["goodbye_handling"],
            "Goodbye Handling Outcome", "Category", "Number of Conversations",
            os.path.join(output_dir, "goodbye_handling_bar.html")
        )

    def _generate_png_charts(self, stats: Dict, output_dir: str):
        """降级 PNG 图表（复用原有 analyze_all 中的逻辑）"""
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

    def analyze(self, trace_path: str, output_dir: str, **kwargs) -> None:
        if not os.path.exists(trace_path):
            raise FileNotFoundError(f"Trace file not found: {trace_path}")
        os.makedirs(output_dir, exist_ok=True)

        with open(trace_path, "r", encoding="utf-8") as f:
            traces = json.load(f)
        print(f"Loaded {len(traces)} conversations from {trace_path}")

        stats = analyze_traces_data(traces)

        # 保存文本报告
        self._save_text_report(stats, os.path.join(output_dir, "analysis_report.txt"))

        # 生成图表
        if self.format == "html" and HAS_PLOTLY:
            self._generate_html_charts(stats, output_dir)
        elif self.format == "png":
            self._generate_png_charts(stats, output_dir)
        else:
            print(f"Format '{self.format}' not supported or plotly missing, skipping charts.")


