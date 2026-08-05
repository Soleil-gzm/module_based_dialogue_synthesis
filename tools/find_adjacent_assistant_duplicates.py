#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
分析 JSON 文件中每个对话的 messages 列表，
按顺序找出相邻的 assistant 消息（中间可能隔了 user），
如果它们的内容（忽略数字后）相同，则判定为重复，
将包含重复的对话保存到新的 JSON 文件中。
"""

import json
import re
import sys
from pathlib import Path


# ========== 硬编码配置 ==========
INPUT_JSON = "tool_analysis/data/data-backbone-due-2w-variants-260723.json"       # 输入 JSON 文件路径
OUTPUT_JSON = "tool_analysis/data-backbone-due-2w-variants-260723_clean_duplicates1.json"  # 输出 JSON 文件路径
# ===================================


def normalize_content(text: str) -> str:
    """归一化：移除所有数字，忽略金额、日期等占位符差异"""
    return re.sub(r'\d+', '', text)


def find_adjacent_assistant_duplicates(messages):
    """
    提取所有 assistant 消息（按顺序），
    比较第 N 个和第 N+1 个 assistant 的内容（忽略数字后是否相同）。
    返回列表，每个元素为 (index1, index2, content1, content2)。
    """
    # 1. 按顺序提取所有 assistant 消息的 (索引, content)
    assistants = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant":
            assistants.append((i, msg.get("content", "")))

    # 2. 如果 assistant 少于 2 个，不可能有重复
    if len(assistants) < 2:
        return []

    duplicates = []
    # 3. 两两比较（第0个和第1个，第1个和第2个，以此类推）
    for j in range(len(assistants) - 1):
        idx1, content1 = assistants[j]
        idx2, content2 = assistants[j + 1]
        if normalize_content(content1) == normalize_content(content2):
            duplicates.append((idx1, idx2, content1, content2))

    return duplicates


def main():
    input_path = Path(INPUT_JSON)
    output_path = Path(OUTPUT_JSON)

    if not input_path.exists():
        print(f"❌ 输入文件不存在: {input_path}")
        sys.exit(1)

    print(f"📌 读取文件: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("❌ 输入 JSON 文件根元素不是列表，请检查格式。")
        sys.exit(1)

    total_conversations = len(data)
    print(f"✅ 共加载 {total_conversations} 个对话")

    result_data = []

    for idx, dialogue in enumerate(data):
        messages = dialogue.get("messages", [])
        if not messages:
            continue
        duplicates = find_adjacent_assistant_duplicates(messages)
        if duplicates:
            dialogue_copy = dialogue.copy()
            dialogue_copy["_has_adjacent_assistant_duplicate"] = True
            dialogue_copy["_duplicate_pairs"] = duplicates
            result_data.append(dialogue_copy)
            print(f"   ✅ 对话 {idx} 存在 {len(duplicates)} 对重复的相邻 assistant 消息")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f"\n📊 共找到 {len(result_data)} 个存在相邻 assistant 重复的对话")
    print(f"📄 结果已保存至: {output_path}")


if __name__ == "__main__":
    main()