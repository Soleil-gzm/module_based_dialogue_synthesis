#!/usr/bin/env python3
"""
模块条件 + UID 多样性分析工具
用法: python analyze_module_diversity.py <trace_file.json> --module 信息问题

输出:
  1. 热力图: 条件 vs UID 选择次数
  2. 集中度条形图: 每个条件下最常用 UID 的占比（越接近 1，越单调）
  3. 文本报告: 每个条件的 UID 数量、总次数、最大占比
"""
import json
import sys
import argparse
from collections import defaultdict, Counter
from pathlib import Path

import numpy as np
import pandas as pd

# ===== 中文字体设置 =====
import matplotlib
matplotlib.use('Agg')  # 无 GUI 环境
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 尝试找到可用的中文字体
font_candidates = [
    'WenQuanYi Micro Hei',
    'WenQuanYi Zen Hei',
    'Noto Sans CJK SC',
    'SimHei',
    'Microsoft YaHei',
    'DejaVu Sans'
]
available_fonts = {f.name for f in fm.fontManager.ttflist}
chosen_font = next((f for f in font_candidates if f in available_fonts), None)

if chosen_font:
    plt.rcParams['font.sans-serif'] = [chosen_font] + plt.rcParams['font.sans-serif']
else:
    print("⚠️ 未找到中文字体，图表中文可能显示为方块。")
    print("   请安装: sudo apt-get install fonts-wqy-microhei fonts-wqy-zenhei")

plt.rcParams['axes.unicode_minus'] = False  # 负号显示
# ===== 设置结束 =====

def analyze_module_diversity(trace_file: str, target_module: str, top_conditions: int = 15):
    """分析指定模块的条件分布和 UID 多样性"""
    
    with open(trace_file, 'r', encoding='utf-8') as f:
        traces = json.load(f)
    
    print(f"✅ 加载追踪数据: {len(traces)} 条对话")
    
    # ===== 数据提取: (条件, UID) -> 计数 =====
    condition_uid_counter = defaultdict(Counter)
    condition_total_counter = Counter()
    
    for trace in traces:
        for mod in trace.get('modules', []):
            if mod.get('module') != target_module:
                continue
            
            cond_text = mod.get('condition_text', '')
            if not cond_text or cond_text == '无条件':
                cond_text = '无条件(空)'
            
            uid = mod.get('selected_uid', -1)
            if uid == -1:
                continue
            
            condition_uid_counter[cond_text][uid] += 1
            condition_total_counter[cond_text] += 1
    
    if not condition_uid_counter:
        print(f"⚠️ 模块 '{target_module}' 无数据")
        return
    
    # ===== 1. 文本报告 =====
    print("\n" + "=" * 80)
    print(f"📊 模块 '{target_module}' 条件 × UID 多样性报告")
    print("=" * 80)
    
    # 只取 Top N 条件（按总次数排序），防止画图时太拥挤
    sorted_conditions = condition_total_counter.most_common(top_conditions)
    top_condition_names = [c for c, _ in sorted_conditions]
    
    print(f"共 {len(top_condition_names)} 个条件 (显示 Top {len(top_condition_names)})")
    print("-" * 80)
    print(f"{'条件':<30} {'总次数':>8} {'不同UID数':>10} {'最大UID占比':>12} {'多样性评分':>10}")
    print("-" * 80)
    
    diversity_scores = []
    for cond in top_condition_names:
        uid_counts = condition_uid_counter[cond]
        total = condition_total_counter[cond]
        unique_uids = len(uid_counts)
        max_count = max(uid_counts.values()) if uid_counts else 0
        max_ratio = max_count / total if total > 0 else 0
        
        # 多样性评分: 1 - (最大占比) ，越接近 1 表示越均匀
        diversity = 1 - max_ratio
        
        print(f"{cond:<30} {total:>8} {unique_uids:>10} {max_ratio:>11.2%} {diversity:>9.2f}")
        diversity_scores.append({
            'condition': cond,
            'total': total,
            'unique_uids': unique_uids,
            'max_ratio': max_ratio,
            'diversity': diversity,
            'uid_counts': uid_counts
        })
    
    # ===== 2. 热力图 (条件 vs UID) =====
    # 构建 DataFrame: 行=条件, 列=UID
    # 限制 UID 数量：只取所有条件中出现的 Top 20 UID（避免太宽）
    all_uids = Counter()
    for cond in top_condition_names:
        for uid, cnt in condition_uid_counter[cond].items():
            all_uids[uid] += cnt
    
    top_uids = [uid for uid, _ in all_uids.most_common(20)]
    
    # 构建矩阵
    matrix_data = []
    for cond in top_condition_names:
        row = []
        for uid in top_uids:
            row.append(condition_uid_counter[cond].get(uid, 0))
        matrix_data.append(row)
    
    df_heatmap = pd.DataFrame(matrix_data, index=top_condition_names, columns=top_uids)
    
    # 画图
    fig, ax = plt.subplots(figsize=(max(10, len(top_uids) * 0.5), max(6, len(top_condition_names) * 0.4)))
    
    # 如果数据量小，显示数值；如果数据量大，只显示颜色
    annot = len(top_uids) <= 15 and len(top_condition_names) <= 15
    
    im = ax.imshow(df_heatmap.values, cmap='YlOrRd', aspect='auto')
    
    # 设置刻度
    ax.set_xticks(np.arange(len(top_uids)))
    ax.set_yticks(np.arange(len(top_condition_names)))
    ax.set_xticklabels(top_uids, rotation=90, fontsize=8)
    ax.set_yticklabels(top_condition_names, fontsize=9)
    
    # 添加数值标注（如果数据量小）
    if annot:
        for i in range(len(top_condition_names)):
            for j in range(len(top_uids)):
                val = df_heatmap.values[i, j]
                if val > 0:
                    ax.text(j, i, str(val), ha='center', va='center', color='black' if val < 5 else 'white', fontsize=8)
    
    # 颜色条
    plt.colorbar(im, ax=ax, label='选择次数')
    
    ax.set_xlabel('话术行 UID', fontsize=12)
    ax.set_ylabel('条件', fontsize=12)
    ax.set_title(f'模块 "{target_module}" 条件 × UID 选择热力图\n(仅显示 Top {len(top_uids)} 个 UID, Top {len(top_condition_names)} 个条件)', fontsize=13)
    
    plt.tight_layout()
    
    # 保存热力图
    output_dir = Path(trace_file).parent.parent / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    heatmap_file = output_dir / f"diversity_heatmap_{target_module}.png"
    plt.savefig(heatmap_file, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"\n✅ 热力图已保存: {heatmap_file}")
    
    # ===== 3. 集中度条形图 =====
    fig, ax = plt.subplots(figsize=(max(10, len(top_condition_names) * 0.4), 6))
    
    conds = [d['condition'] for d in diversity_scores]
    ratios = [d['max_ratio'] for d in diversity_scores]
    unique_counts = [d['unique_uids'] for d in diversity_scores]
    
    # 绘制条形图：柱子高度 = 最大UID占比，颜色根据多样性渐变
    colors = plt.cm.RdYlGn_r([d['diversity'] for d in diversity_scores])  # 多样性高 = 绿色
    bars = ax.barh(conds, ratios, color=colors, edgecolor='black', alpha=0.85)
    
    # 在条形末尾添加 UID 数量标注
    for bar, unique_cnt, ratio in zip(bars, unique_counts, ratios):
        ax.text(ratio + 0.02, bar.get_y() + bar.get_height()/2, 
                f'UID:{unique_cnt}  占比:{ratio:.1%}', 
                va='center', fontsize=9)
    
    ax.axvline(x=0.5, color='red', linestyle='--', linewidth=1.5, alpha=0.6, label='多样性警戒线 (占比50%)')
    
    ax.set_xlabel('最常用 UID 的占比 (越接近 1 越单调)', fontsize=12)
    ax.set_ylabel('条件', fontsize=12)
    ax.set_title(f'模块 "{target_module}" 话术多样性集中度分析\n(占比越高，说明该条件越依赖某一句固定话术)', fontsize=13)
    ax.legend(loc='lower right')
    ax.grid(axis='x', linestyle='--', alpha=0.3)
    ax.set_xlim(0, 1.1)
    
    plt.tight_layout()
    
    # 保存集中度图
    diversity_file = output_dir / f"diversity_concentration_{target_module}.png"
    plt.savefig(diversity_file, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ 集中度图已保存: {diversity_file}")
    
    # ===== 4. 文本报告保存 =====
    report_file = output_dir / f"diversity_report_{target_module}.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"模块 '{target_module}' 条件 × UID 多样性报告\n")
        f.write("=" * 80 + "\n")
        f.write(f"{'条件':<30} {'总次数':>8} {'不同UID数':>10} {'最大UID占比':>12} {'多样性评分':>10}\n")
        f.write("-" * 80 + "\n")
        for d in diversity_scores:
            f.write(f"{d['condition']:<30} {d['total']:>8} {d['unique_uids']:>10} {d['max_ratio']:>11.2%} {d['diversity']:>9.2f}\n")
        f.write("\n" + "=" * 80 + "\n")
        f.write("解读指南:\n")
        f.write("- '最大UID占比' 越接近 100% ，说明该条件只命中固定的1-2句话术，多样性差。\n")
        f.write("- '多样性评分' 越接近 1.0 ，说明该条件下各 UID 分布越均匀。\n")
        f.write("- 建议关注 '最大UID占比 > 50%' 的条件，检查 Excel 里的 'parent(继承)' 或 'flexible_stop' 是否限制了随机性。\n")
    
    print(f"✅ 文本报告已保存: {report_file}")
    
    # 打印高亮提醒
    print("\n" + "=" * 80)
    print("⚠️ 多样性警报 (建议关注以下条件):")
    alert_count = 0
    for d in diversity_scores:
        if d['max_ratio'] > 0.5:
            print(f"  🔴 {d['condition']}: 最大UID占比 {d['max_ratio']:.1%} (仅 {d['unique_uids']} 个不同UID)")
            alert_count += 1
    if alert_count == 0:
        print("  ✅ 所有条件多样性良好，无明显单调问题。")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="分析模块的条件分布和 UID 多样性")
    parser.add_argument("trace_file", help="trace JSON 文件路径")
    parser.add_argument("--module", "-m", required=True, help="要分析的模块名称 (如: 信息问题)")
    parser.add_argument("--top", "-n", type=int, default=15, help="显示前 N 个条件 (默认: 15)")
    args = parser.parse_args()
    
    if not Path(args.trace_file).exists():
        print(f"❌ 文件不存在: {args.trace_file}")
        sys.exit(1)
    
    analyze_module_diversity(args.trace_file, args.module, args.top)


if __name__ == "__main__":
    main()