"""
对话去重模块：删除相邻且内容重复/高度相似的 user+assistant 轮次

功能说明：
1. 按顺序提取每个对话中的所有 assistant 消息
2. 比较相邻的 assistant（中间可隔 user），判断是否重复
3. 支持忽略数字（金额、日期等占位符）
4. 支持相似度阈值控制（0.0~1.0），阈值越高越严格
5. 保留第一次出现的轮次，删除后续重复轮次
6. 删除时同时删除 assistant 和它前面的 user 消息

使用示例：
    from deduplicate_assistant import process
    
    # 严格去重（归一化后完全相同才删除）
    cleaned = process(data, threshold=1.0)
    
    # 相似度 >= 0.85 即视为重复
    cleaned = process(data, threshold=0.85, ignore_numbers=True)
    
    # 不忽略数字，且要求完全相同
    cleaned = process(data, threshold=1.0, ignore_numbers=False)
"""

import re
from difflib import SequenceMatcher


def normalize_content(text: str, ignore_numbers: bool = True) -> str:
    """
    归一化文本，用于比较。
    :param text: 输入文本
    :param ignore_numbers: 是否移除数字（金额、日期等占位符）
    :return: 归一化后的文本
    """
    if ignore_numbers:
        return re.sub(r'\d+', '', text)
    return text


def calculate_similarity(text1: str, text2: str, ignore_numbers: bool = True) -> float:
    """
    计算两个文本的相似度（归一化后的字符级相似度）。
    :param text1: 文本1
    :param text2: 文本2
    :param ignore_numbers: 是否忽略数字
    :return: 相似度分数 0.0~1.0
    """
    s1 = normalize_content(text1, ignore_numbers)
    s2 = normalize_content(text2, ignore_numbers)
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1, s2).ratio()


def is_similar(text1: str, text2: str, threshold: float, ignore_numbers: bool = True) -> tuple:
    """
    判断两个文本是否相似（基于归一化后的字符级相似度）。
    :param text1: 文本1
    :param text2: 文本2
    :param threshold: 相似度阈值 0.0~1.0
    :param ignore_numbers: 是否忽略数字
    :return: (是否相似, 相似度分数)
    """
    score = calculate_similarity(text1, text2, ignore_numbers)
    if threshold >= 1.0:
        return (score >= 0.9999), score  # 浮点数容差
    return (score >= threshold), score


def process(data, threshold: float = 1.0, ignore_numbers: bool = True, keep: str = 'first'):
    """
    去除相邻且内容（忽略数字后）重复或高度相似的 user+assistant 轮次。
    保留第一次出现的轮次，删除后续重复轮次。

    :param data: 对话列表（json.load 后的对象），会原地修改
    :param threshold: 相似度阈值 0.0~1.0，默认 1.0 表示必须完全相同。
                      设为 0.85 表示相似度 >= 85% 视为重复。
    :param ignore_numbers: 是否忽略数字（金额、日期等占位符），默认 True
    :param keep: 保留策略，'first' 保留第一次出现，'last' 保留最后一次出现
    :return: 处理后的对话列表（同 data）
    """
    # 参数校验
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold 必须在 0.0~1.0 之间，当前值: {threshold}")
    if keep not in ('first', 'last'):
        raise ValueError(f"keep 必须是 'first' 或 'last'，当前值: {keep}")

    for dialogue in data:
        messages = dialogue.get('messages', [])
        if len(messages) < 4:  # 至少需要 user+assistant+user+assistant 才可能重复
            continue

        # 1. 提取所有 assistant 消息的索引和内容
        assistant_indices = []
        for i, msg in enumerate(messages):
            if msg.get('role') == 'assistant':
                assistant_indices.append(i)

        if len(assistant_indices) < 2:
            continue

        # 2. 从前往后或从后往前比较相邻 assistant
        to_remove = set()

        if keep == 'first':
            # 保留第一次出现：从前往后遍历，删除后续重复
            range_iter = range(len(assistant_indices) - 1)
            compare_func = lambda i, j: i < j  # 删除索引更大的
        else:
            # 保留最后一次出现：从后往前遍历，删除前面的重复
            range_iter = range(len(assistant_indices) - 2, -1, -1)
            compare_func = lambda i, j: i > j  # 删除索引更小的

        for i in range_iter:
            idx1 = assistant_indices[i]
            idx2 = assistant_indices[i + 1] if keep == 'first' else assistant_indices[i]

            # 如果其中一个已经被标记删除，跳过
            if idx1 in to_remove or idx2 in to_remove:
                continue

            content1 = messages[idx1].get('content', '')
            content2 = messages[idx2].get('content', '')
            sim, score = is_similar(content1, content2, threshold, ignore_numbers)

            if sim:
                # 确定要删除哪个 assistant
                if keep == 'first':
                    del_idx = idx2  # 删除后面的
                else:
                    del_idx = idx1  # 删除前面的
                to_remove.add(del_idx)

                # 找到它前面的 user 消息并删除
                # 注意：user 可能在 assistant 前面，也可能在 assistant 后面
                # 标准格式：... user, assistant ... 所以向前查找
                user_idx = del_idx - 1
                if user_idx >= 0 and messages[user_idx].get('role') == 'user':
                    to_remove.add(user_idx)
                else:
                    # 向前查找最近的 user（防御性编程）
                    for j in range(del_idx - 1, -1, -1):
                        if messages[j].get('role') == 'user':
                            to_remove.add(j)
                            break

        # 3. 删除标记的索引
        if to_remove:
            dialogue['messages'] = [msg for idx, msg in enumerate(messages) if idx not in to_remove]

    return data
