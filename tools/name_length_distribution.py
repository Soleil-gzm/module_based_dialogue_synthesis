#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统计 txt 文件中所有 "客户姓名：XXX" 的姓名字数分布，生成 HTML 图表。
同时将三个字及以上的姓名导出到单独的 txt 文件。
"""

import re
import sys
from pathlib import Path
from collections import Counter

try:
    import plotly.express as px
    import pandas as pd
except ImportError:
    print("❌ 缺少 plotly 或 pandas 依赖，请执行: pip install plotly pandas")
    sys.exit(1)


# ========== 硬编码配置 ==========
INPUT_DIR = "datas/suning/due/cases2_replace"
OUTPUT_HTML = "tool_analysis/due_sunig/name_length_distribution.html"
MIN_LENGTH_TO_EXPORT = 4   # 导出姓名的最小长度（包含该长度）
# ===================================


def extract_names_from_file(file_path: Path) -> list:
    """从 txt 文件中提取所有 '客户姓名：XXX' 中的姓名"""
    names = []
    pattern = re.compile(r"客户姓名[：:]\s*([^\s，,。]+)")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                matches = pattern.findall(line)
                names.extend(matches)
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                for line in f:
                    matches = pattern.findall(line)
                    names.extend(matches)
        except Exception as e:
            print(f"⚠️ 无法读取文件 {file_path}: {e}")
    except Exception as e:
        print(f"⚠️ 读取文件 {file_path} 出错: {e}")
    return names


def get_name_length(name: str) -> int:
    """返回姓名中中文字符的个数（忽略非中文字符）"""
    chinese_chars = [c for c in name if '\u4e00' <= c <= '\u9fff']
    return len(chinese_chars)


def main():
    input_dir = Path(INPUT_DIR)
    if not input_dir.exists():
        print(f"❌ 输入目录不存在: {input_dir}")
        sys.exit(1)

    all_names = []
    for txt_file in input_dir.rglob("*.txt"):
        names = extract_names_from_file(txt_file)
        all_names.extend(names)
        print(f"✅ 从 {txt_file} 提取了 {len(names)} 个姓名")

    if not all_names:
        print("⚠️ 未找到任何姓名，请检查文件内容和 '客户姓名：' 格式。")
        sys.exit(0)

    # 统计字数分布
    length_counter = Counter()
    for name in all_names:
        length = get_name_length(name)
        length_counter[length] += 1

    # ---------- 导出指定长度及以上的姓名 ----------
    output_dir = Path(OUTPUT_HTML).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    long_names = [name for name in all_names if get_name_length(name) >= MIN_LENGTH_TO_EXPORT]
    if long_names:
        export_file = output_dir / f"names_length_ge{MIN_LENGTH_TO_EXPORT}.txt"
        with open(export_file, 'w', encoding='utf-8') as f:
            for name in long_names:
                f.write(name + '\n')
        print(f"\n✅ 导出 {len(long_names)} 个姓名（长度 ≥ {MIN_LENGTH_TO_EXPORT}）到 {export_file}")
    else:
        print(f"\n⚠️ 没有姓名长度 ≥ {MIN_LENGTH_TO_EXPORT}")

    # ---------- 生成 HTML 图表 ----------
    df = pd.DataFrame({
        '字数': sorted(length_counter.keys()),
        '人数': [length_counter[k] for k in sorted(length_counter.keys())]
    })

    fig = px.bar(df, x='字数', y='人数',
                 title='客户姓名字数分布',
                 labels={'字数': '姓名长度（字）', '人数': '人数'},
                 text='人数',
                 color_discrete_sequence=['#1f77b4'])

    fig.update_traces(textposition='outside')
    fig.update_layout(
        xaxis=dict(tickmode='linear', tick0=1, dtick=1),
        yaxis=dict(title='人数'),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(size=14)
    )

    output_path = Path(OUTPUT_HTML)
    fig.write_html(str(output_path))

    print(f"\n✅ 统计完成！共提取 {len(all_names)} 个姓名")
    print(f"📊 字数分布: {dict(sorted(length_counter.items()))}")
    print(f"📄 图表已保存至: {output_path}")


if __name__ == "__main__":
    main()