import re

def normalize(text):
    return re.sub(r'\d+', '', text)

def process(data):
    """
    去除相邻且内容重复的 user+assistant 轮次。
    data: 对话列表（json.load 后的对象）
    return: 处理后的对话列表
    """
    for dialogue in data:
        messages = dialogue.get('messages', [])
        if not messages:
            continue

        assistant_indices = [i for i, m in enumerate(messages) if m.get('role') == 'assistant']
        if len(assistant_indices) < 2:
            continue

        to_remove = set()
        for i in range(len(assistant_indices) - 1):
            idx1 = assistant_indices[i]
            idx2 = assistant_indices[i + 1]
            if normalize(messages[idx1].get('content', '')) == normalize(messages[idx2].get('content', '')):
                to_remove.add(idx2)
                # 找前面的 user
                for j in range(idx2 - 1, -1, -1):
                    if messages[j].get('role') == 'user':
                        to_remove.add(j)
                        break

        if to_remove:
            dialogue['messages'] = [m for idx, m in enumerate(messages) if idx not in to_remove]

    return data