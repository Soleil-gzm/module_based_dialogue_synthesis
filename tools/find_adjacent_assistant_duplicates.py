#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
分析 JSON 文件中每个对话的 messages 列表，
按顺序找出相邻的 assistant 消息（中间可能隔了 user），
如果它们的内容（可忽略数字）相似度 >= 设定的阈值，则判定为重复，
将包含此类重复的对话保存到新的 JSON 文件中。
"""

import json
import re
import sys
from pathlib import Path
from difflib import SequenceMatcher


# ========== 硬编码配置 ==========
INPUT_JSON = "tool_analysis/data/data-backbone-due-2w-variants-260723.json"
OUTPUT_JSON = "tool_analysis/data-backbone-due-2w-variants-260723_clean_duplicates0.6.json"
SIMILARITY_THRESHOLD = 0.6   # 0.0~1.0，设为 1.0 表示必须完全相同
IGNORE_NUMBERS = True         # 是否忽略数字（金额、日期等占位符）
# ===================================


def normalize_content(text: str, ignore_numbers: bool = True) -> str:
    """归一化文本，可选择是否移除数字"""
    if ignore_numbers:
        return re.sub(r'\d+', '', text)
    return text

def find_adjacent_assistant_duplicates(messages, threshold: float, ignore_numbers: bool):
    """
    提取所有 assistant 消息（按顺序），
    比较第 N 个和第 N+1 个 assistant 的内容（忽略数字后是否相同）。
    返回列表，每个元素为 (index1, index2, content1, content2, similarity_score)。
    """
    assistants = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant":
            assistants.append((i, msg.get("content", "")))

    if len(assistants) < 2:
        return []

    duplicates = []
    for j in range(len(assistants) - 1):
        idx1, content1 = assistants[j]
        idx2, content2 = assistants[j + 1]
        # 计算相似度
        s1 = normalize_content(content1, ignore_numbers)
        s2 = normalize_content(content2, ignore_numbers)
        if threshold >= 1.0:
            is_dup = (s1 == s2)
            score = 1.0 if is_dup else 0.0
        else:
            score = SequenceMatcher(None, s1, s2).ratio()
            is_dup = (score >= threshold)
        if is_dup:
            duplicates.append((idx1, idx2, content1, content2, score))

    return duplicates


def main():
    input_path = Path(INPUT_JSON)
    output_path = Path(OUTPUT_JSON)

    if not input_path.exists():
        print(f"❌ 输入文件不存在: {input_path}")
        sys.exit(1)

    print(f"📌 读取文件: {input_path}")
    print(f"📌 相似度阈值: {SIMILARITY_THRESHOLD}")
    print(f"📌 忽略数字: {IGNORE_NUMBERS}")

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
        duplicates = find_adjacent_assistant_duplicates(messages, SIMILARITY_THRESHOLD, IGNORE_NUMBERS)
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