"""
对话去重模块：删除相邻且内容重复/高度相似的 user+assistant 轮次
策略：保留第一次出现的轮次，删除后续重复的轮次
"""

import re
from difflib import SequenceMatcher


def normalize_content(text: str, ignore_numbers: bool = True) -> str:
    """归一化文本，可选择是否移除数字"""
    if ignore_numbers:
        return re.sub(r'\d+', '', text)
    return text


def calculate_similarity(text1: str, text2: str, ignore_numbers: bool = True) -> float:
    """计算两个文本的相似度（归一化后的字符级相似度）"""
    s1 = normalize_content(text1, ignore_numbers)
    s2 = normalize_content(text2, ignore_numbers)
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1, s2).ratio()


def is_similar(text1: str, text2: str, threshold: float, ignore_numbers: bool = True) -> tuple:
    """判断两个文本是否相似，返回 (是否相似, 相似度分数)"""
    score = calculate_similarity(text1, text2, ignore_numbers)
    if threshold >= 1.0:
        return (score >= 0.9999), score  # 浮点数容差
    return (score >= threshold), score


def process(data, threshold: float = 1.0, ignore_numbers: bool = True):
    """
    去除相邻且内容（忽略数字后）重复或高度相似的 user+assistant 轮次。
    保留第一次出现的轮次，删除后续重复轮次。

    :param data: 对话列表（json.load 后的对象），会原地修改
    :param threshold: 相似度阈值 0.0~1.0，默认 1.0 表示必须完全相同
    :param ignore_numbers: 是否忽略数字，默认 True
    :return: 处理后的对话列表（同 data）
    """
    # 参数校验
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold 必须在 0.0~1.0 之间，当前值: {threshold}")

    for dialogue in data:
        messages = dialogue.get('messages', [])
        if len(messages) < 4:  # 至少需要 user+assistant+user+assistant 才可能重复
            continue

        # 1. 提取所有 assistant 消息的索引
        assistant_indices = [i for i, msg in enumerate(messages) if msg.get('role') == 'assistant']
        if len(assistant_indices) < 2:
            continue

        to_remove = set()

        # 2. 从前往后遍历，比较相邻 assistant
        for i in range(len(assistant_indices) - 1):
            idx1 = assistant_indices[i]
            idx2 = assistant_indices[i + 1]

            # 如果其中一个已经被标记删除，跳过
            if idx1 in to_remove or idx2 in to_remove:
                continue

            content1 = messages[idx1].get('content', '')
            content2 = messages[idx2].get('content', '')
            sim, _ = is_similar(content1, content2, threshold, ignore_numbers)

            if sim:
                # 删除后面的 assistant (idx2)
                to_remove.add(idx2)

                # 删除它前面的 user
                user_idx = idx2 - 1
                if user_idx >= 0 and messages[user_idx].get('role') == 'user':
                    to_remove.add(user_idx)
                else:
                    for j in range(idx2 - 1, -1, -1):
                        if messages[j].get('role') == 'user':
                            to_remove.add(j)
                            break

        # 3. 重建 messages（跳过被标记的索引）
        if to_remove:
            dialogue['messages'] = [msg for idx, msg in enumerate(messages) if idx not in to_remove]

    return data
