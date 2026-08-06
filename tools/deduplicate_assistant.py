"""
对话去重模块：删除相邻且内容重复/高度相似的 user+assistant 轮次
策略：保留第一次出现的轮次，删除后续重复的轮次
支持返回统计信息
"""

import re
from difflib import SequenceMatcher


def normalize_content(text: str, ignore_numbers: bool = True) -> str:
    if ignore_numbers:
        return re.sub(r'\d+', '', text)
    return text


def calculate_similarity(text1: str, text2: str, ignore_numbers: bool = True) -> float:
    s1 = normalize_content(text1, ignore_numbers)
    s2 = normalize_content(text2, ignore_numbers)
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1, s2).ratio()


def is_similar(text1: str, text2: str, threshold: float, ignore_numbers: bool = True) -> tuple:
    score = calculate_similarity(text1, text2, ignore_numbers)
    if threshold >= 1.0:
        return (score >= 0.9999), score
    return (score >= threshold), score


def process(data, threshold: float = 1.0, ignore_numbers: bool = True, return_stats: bool = False):
    """
    去除相邻且重复/高度相似的 user+assistant 轮次，保留第一次出现。

    :param data: 对话列表（json.load 后的对象），会原地修改
    :param threshold: 相似度阈值 0.0~1.0
    :param ignore_numbers: 是否忽略数字
    :param return_stats: 是否返回统计信息，默认 False 只返回处理后的数据
    :return: 如果 return_stats=False，返回处理后的 data；否则返回 (data, stats_dict)
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold 必须在 0.0~1.0 之间，当前值: {threshold}")

    stats = {
        'total_dialogues': len(data),
        'duplicate_dialogues': 0,   # 对重复的对话数
        'removed_pairs': 0,         # 删除的 user+assistant 轮对数
        'modified_dialogues': 0,    # 实际修改了 messages 的对话数
    }

    for dialogue in data:
        messages = dialogue.get('messages', [])
        if len(messages) < 4:
            continue

        assistant_indices = [i for i, msg in enumerate(messages) if msg.get('role') == 'assistant']
        if len(assistant_indices) < 2:
            continue

        to_remove = set()
        has_dup = False
        removed_in_dialogue = 0

        for i in range(len(assistant_indices) - 1):
            idx1 = assistant_indices[i]
            idx2 = assistant_indices[i + 1]

            if idx1 in to_remove or idx2 in to_remove:
                continue

            content1 = messages[idx1].get('content', '')
            content2 = messages[idx2].get('content', '')
            sim, _ = is_similar(content1, content2, threshold, ignore_numbers)

            if sim:
                # 标记删除后面的 assistant
                to_remove.add(idx2)
                removed_in_dialogue += 1
                has_dup = True

                # 删除它前面的 user
                user_idx = idx2 - 1
                if user_idx >= 0 and messages[user_idx].get('role') == 'user':
                    to_remove.add(user_idx)
                else:
                    for j in range(idx2 - 1, -1, -1):
                        if messages[j].get('role') == 'user':
                            to_remove.add(j)
                            break

        if to_remove:
            dialogue['messages'] = [msg for idx, msg in enumerate(messages) if idx not in to_remove]
            stats['modified_dialogues'] += 1

        if has_dup:
            stats['duplicate_dialogues'] += 1
            stats['removed_pairs'] += removed_in_dialogue

    if return_stats:
        return data, stats
    return data
