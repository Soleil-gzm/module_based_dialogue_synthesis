#!/usr/bin/env python3
"""
多轮对话生成脚本（基于 Excel 模块和概率矩阵）
读取对话模块分类 Excel 和概率矩阵，生成大量模拟对话 JSON。
输出格式与清洗项目兼容：{"messages": [{"role": "system", ...}, {"role": "user", ...}, ...]}
"""

import os
import json
import random
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

# ========== 调试与日志配置 ==========
DEBUG_MODE = True   # 全局调试开关，可改为 False 关闭详细日志
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
log_filename = os.path.join(LOG_DIR, f"dialogue_builder_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# 配置 logging：同时输出到控制台和文件
logging.basicConfig(
    level=logging.DEBUG if DEBUG_MODE else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ========== 配置参数（请根据实际路径修改）==========
EXCEL_PATH = "datas/对话模块分类 - 洋钱罐 - 1111.xlsx"
PROB_PATH = "datas/prob.xlsx"
CASES_DIR = "datas/cases_random"
OUTPUT_DIR = "output"
NUM_PATHS = 40000            # 生成对话数量
RANDOM_SEED = 42             # 随机种子，保证可复现

# 模块列表（与 Excel 中的 sheet 名称一致）
MODULES = [
    '核实', '三方', '转告', '告知', '承诺还款', '非明确承诺还款',
    '资金困难', '信息问题', '用卡及征信', '无法沟通', '放时间应对',
    '特殊情况', '年费及可用额度', '投诉处理', '联系三方应对',
    '要求停催应对', '要求领导回电应对', '转人工及挂机'
]

# 每个模块的最大重复次数（从 possible_times 映射）
MAX_REPEAT = {
    '核实': 4, '三方': 2, '转告': 2, '告知': 2, '承诺还款': 2,
    '非明确承诺还款': 3, '资金困难': 4, '信息问题': 4, '用卡及征信': 3,
    '无法沟通': 3, '放时间应对': 3, '特殊情况': 3, '年费及可用额度': 2,
    '投诉处理': 3, '联系三方应对': 2, '要求停催应对': 3,
    '要求领导回电应对': 2, '转人工及挂机': 3
}

# 特殊模块：达到最大次数后仅禁用该模块，不终止对话
SPECIAL_NODES = {'特殊情况', '信息问题', '用卡及征信'}

# 可以附加衔接施压话术的模块
INSERT_NODES = {'资金困难', '用卡及征信', '放时间应对'}

# ========== 辅助函数 ==========
def load_sheets(excel_path):
    """加载所有工作表，保留 conditions 包含 S1|S2 的行，存储到 df_dict"""
    df_dict = {}
    for sheet in MODULES:
        df = pd.read_excel(excel_path, sheet_name=sheet)
        # 筛选 conditions 列包含 S1|S2 的行
        mask = df['conditions(条件)'].apply(lambda x: isinstance(x, str) and 'S1|S2' in x)
        df_filtered = df[mask].copy()
        # 去掉 human 列中包含 <随机金额> 或 <随机时间> 的行（原始逻辑）
        df_filtered = df_filtered[~df_filtered['human(客户)'].str.contains('<随机金额>|<随机时间>', na=False)]
        df_dict[sheet] = df_filtered
    return df_dict

def load_prob_matrix(prob_path, modules):
    """加载概率矩阵并标准化为 DataFrame，行列顺序与 modules 一致,prob.xlsx 是纯数值矩阵（无行列标签）"""
    prob_df = pd.read_excel(prob_path, header=None)
    prob_df.columns = modules
    prob_df.index = modules
    prob_df = prob_df / 100.0
    return prob_df

def parse_case_info(txt_path):
    """解析案例文件，返回字段字典"""
    data = {}
    with open(txt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for line in lines:
        line = line.strip()
        if line.startswith('- 专员工号'):
            data['专员工号'] = line.split('：')[1].strip()
        elif line.startswith('- 姓名'):
            data['姓名'] = line.split('：')[1].strip()
        elif line.startswith('- 性别'):
            gender = line.split('：')[1].strip()
            data['性别'] = '先生' if gender == '男' else '女士'
        elif line.startswith('- 最大逾期天数'):
            data['最大逾期天数'] = line.split('：')[1].strip()
        elif line.startswith('- 银行查账时间'):
            data['银行查账时间'] = line.split('：')[1].strip()
        elif line.startswith('- 逾期笔数'):
            data['逾期笔数'] = line.split('：')[1].strip()
        elif line.startswith('- 逾期金额'):
            amounts_str = line.split('：')[1].strip()
            amounts = [x.strip() for x in amounts_str.split('，')]
            data['逾期金额1'] = min(amounts, key=lambda x: float(x))  # 取最小一笔
            data['逾期金额列表'] = amounts
        elif line.startswith('- 剩余总待还'):
            data['剩余总待还'] = line.split('：')[1].strip()
    # 生成随机金额：总待还的 30%~70%
    total = float(data['剩余总待还'])
    data['随机金额'] = str(round(total * random.uniform(0.3, 0.7)))
    return data

def get_full_prompt(txt_path):
    """读取整个 case 文件内容作为 system prompt 的后半部分，用于构造 system prompt。"""
    with open(txt_path, 'r', encoding='utf-8') as f:
        return f.read()

def get_ancestors(uid, df):
    ancestors = []
    while True:
        # 获取父行 uid
        parent_series = df.loc[df['uid'] == uid, 'parent(继承)']
        if parent_series.empty:
            break
        parent_val = parent_series.values[0]
        if pd.isna(parent_val) or parent_val == 0:
            break
        # 查找父行是否存在
        parent_row = df[df['uid'] == parent_val]
        if parent_row.empty:
            break   # 父行被过滤，停止追溯
        ancestors.append(parent_row.iloc[0])
        uid = parent_val
    return list(reversed(ancestors))

def get_random_descendant_chain(uid, df, stop_prob=0.3, max_depth=10):
    """
    递归获取一条随机的后代链（从子行开始，随机选择一条路径直到无子行或触发停止）
    uid: 当前行的 uid
    df: 模块的 DataFrame
    stop_prob: 当子行的 flexible_stop=1 时，以该概率停止继续向下（不再添加更深的后代）
    max_depth: 最大递归深度，防止无限循环
    返回: list of rows，顺序从直接子行到最末代（不包含当前行）
    """
    children = df[df['parent(继承)'] == uid]
    if children.empty or max_depth <= 0:
        return []
    # 随机选择一个子行
    child_row = children.sample(n=1).iloc[0]
    chain = [child_row]
    # 检查是否继续向下：如果 flexible_stop=1 且随机数小于 stop_prob，则停止
    flex_stop = child_row.get('flexible_stop(可选不继承)', 0)
    if pd.notna(flex_stop) and flex_stop == 1 and random.random() < stop_prob:
        return chain
    # 否则继续递归
    deeper = get_random_descendant_chain(child_row['uid'], df, stop_prob, max_depth-1)
    chain.extend(deeper)
    return chain

def matches_conditions(row, case):
    """通用条件匹配器，支持 & (且) 和 | (或)，优先级 & 高于 |。"""
    cond_str = row.get('conditions(条件)', '')
    if pd.isna(cond_str) or cond_str == '':
        return True

    # 处理括号（如果有）可以后续扩展，这里先按无括号处理
    # 先将 S1|S2 替换为特殊标记，便于后续统一处理
    # 注意：原始 cond_str 中 S1|S2 通常是作为整体出现的
    # 我们将其视为一个原子条件，永远为真（因为我们已预过滤）
    # 但为了不干扰分割，可暂时替换
    import re
    # 匹配 S1|S2 这样的模式（可能前后有 & 或 空格）
    cond_str = re.sub(r'S1\|S2', '__S1_OR_S2__', cond_str)

    # 1. 按 & 分割
    and_parts = cond_str.split('&')
    for and_part in and_parts:
        and_part = and_part.strip()
        if not and_part:
            continue
        # 2. 每个 and_part 内部可能包含 |，表示“或”关系
        or_parts = and_part.split('|')
        sub_ok = False
        for or_part in or_parts:
            or_part = or_part.strip()
            if or_part == '__S1_OR_S2__':
                sub_ok = True
                break
            elif or_part == '性别是先生':
                if case.get('性别') == '先生':
                    sub_ok = True
                    break
            elif or_part == '性别是女士':
                if case.get('性别') == '女士':
                    sub_ok = True
                    break
            elif or_part == '逾期笔数大于1':
                if int(case.get('逾期笔数', 0)) > 1:
                    sub_ok = True
                    break
            elif or_part == '逾期笔数等于1':
                if int(case.get('逾期笔数', 0)) == 1:
                    sub_ok = True
                    break
            elif or_part.startswith('<随机金额>小于<剩余总待还>'):
                # 目前简化：随机金额总是小于剩余总待还
                sub_ok = True
                break
            else:
                # 未知条件，默认忽略（或可根据需求设为 False）
                continue
        # 如果这个 and_part 中的所有 or 条件都不满足，则整体不匹配
        if not sub_ok:
            return False
    return True

def sample_utterance(row, is_human):
    """从一行中随机抽取一个话术（用 / 分割）"""
    col = 'human(客户)' if is_human else 'assistant(专员)'
    text = row[col]
    if pd.isna(text):
        return ''
    options = [s.strip() for s in str(text).split('/') if s.strip()]
    if not options:
        return ''
    return random.choice(options)

def fill_placeholders(text, case):
    """替换文本中的占位符"""
    if not isinstance(text, str):
        return text
    text = text.replace('<专员工号>', case.get('专员工号', ''))
    text = text.replace('<姓名>', case.get('姓名', ''))
    text = text.replace('<性别>', case.get('性别', ''))
    text = text.replace('<最大逾期天数>', str(case.get('最大逾期天数', '')))
    text = text.replace('<银行查账时间>', case.get('银行查账时间', ''))
    text = text.replace('<逾期笔数>', str(case.get('逾期笔数', '')))
    text = text.replace('<逾期金额1>', case.get('逾期金额1', '') + '元')
    text = text.replace('<剩余总待还>', case.get('剩余总待还', '') + '元')
    text = text.replace('<随机金额>', case.get('随机金额', ''))
    text = text.replace('<empty_tag>', '')
    # 随机时间：银行查账时间 + 1~4 小时
    if '<随机时间>' in text:
        base_time = case.get('银行查账时间', '')
        # 简单处理：添加几个小时，假设格式为 "今天下午X点"
        # 更严谨可解析，但为简化，用固定字符串
        random_hour = random.randint(1, 4)
        text = text.replace('<随机时间>', f"{base_time}过后{random_hour}小时")
    return text

def generate_dialogue(path, df_dict, case, prompt_text):
    """根据一条模块路径和一个案例，生成完整对话 messages"""
    messages = []
    # 添加 system 消息
    sys_content = "你是一个洋钱罐的催收专员，请根据客户的情况，使用合适的话术与客户进行沟通，争取让客户承诺还款。\n" + prompt_text
    messages.append({"role": "system", "content": sys_content})

    # 记录每个模块已出现的次数
    node_counts = {}
    # 加载衔接施压话术（三个备选）
    pressure_df = df_dict.get('衔接施压话术', pd.DataFrame())
    pressure_list = []
    for repeat in [1, 2, 3]:
        if not pressure_df.empty:
            sub = pressure_df[pressure_df['repeat(次数)'].apply(
                lambda x: str(repeat) in str(x).split('/') if pd.notna(x) else False)]
            if not sub.empty:
                row = sub.sample(n=1).iloc[0]
                assistant_opt = row['assistant(专员)']
                if pd.notna(assistant_opt):
                    opt_list = [s.strip() for s in assistant_opt.split('/') if s.strip()]
                    if opt_list:
                        pressure_list.append(random.choice(opt_list))
                    else:
                        pressure_list.append('')
                else:
                    pressure_list.append('')
            else:
                pressure_list.append('')
        else:
            pressure_list.append('')
    pressure_idx = 0

    for node in path:
        # 更新重复次数
        node_counts[node] = node_counts.get(node, 0) + 1
        repeat = node_counts[node]
        df_node = df_dict[node]

        # 筛选符合条件的行：repeat 次数匹配
        mask = df_node['repeat(次数)'].apply(
            lambda x: str(repeat) in str(x).split('/') if pd.notna(x) else False)
        candidates = df_node[mask]
        if candidates.empty:
            continue

        # 进一步根据案例条件筛选
        valid_rows = [row for _, row in candidates.iterrows() if matches_conditions(row, case)]
        if not valid_rows:
            logger.debug(f"模块 {node}, repeat={repeat}: 无可用行（条件不匹配或无数据）")
            continue
        row = random.choice(valid_rows)

        # ----- 调试信息记录 -----
        logger.debug(f"选中行 -> 模块: {node}, repeat: {repeat}, uid: {row['uid']}, conditions: {row.get('conditions(条件)', '')}")
        logger.debug(f"案例信息: 姓名={case.get('姓名')}, 性别={case.get('性别')}, 逾期笔数={case.get('逾期笔数')}")
        assistant_full = str(row['assistant(专员)'])
        logger.debug(f"助理话术预览: {assistant_full[:80]}...")
        
        # 校验性别与话术中称呼的一致性
        if '先生' in assistant_full and case.get('性别') == '女士':
            logger.warning(f"性别可能错误: 女性案例但话术包含'先生'，uid={row['uid']}, 姓名={case.get('姓名')}")
        if '女士' in assistant_full and case.get('性别') == '先生':
            logger.warning(f"性别可能错误: 男性案例但话术包含'女士'，uid={row['uid']}, 姓名={case.get('姓名')}")

        # 处理继承链：祖先 + 当前 + 孩子
        turn_list = []  # 每个元素为 (user_text, assistant_text)

        # 1. 祖先
        ancestors = get_ancestors(row['uid'], df_node)
        logger.debug(f"祖先数量: {len(ancestors)}")
        for anc in ancestors:
            user_text = sample_utterance(anc, True)
            assistant_text = sample_utterance(anc, False)
            if user_text or assistant_text:
                turn_list.append((user_text, assistant_text))

        # 2. 当前行
        current_user = sample_utterance(row, True)
        current_assistant = sample_utterance(row, False)
        turn_list.append((current_user, current_assistant))

        # 3. 后代链
        descendant_chain = get_random_descendant_chain(row['uid'], df_node)
        logger.debug(f"后代链长度: {len(descendant_chain)}")
        for desc in descendant_chain:
            user_text = sample_utterance(desc, True)
            assistant_text = sample_utterance(desc, False)
            if user_text or assistant_text:
                turn_list.append((user_text, assistant_text))

        # 附加衔接施压话术（仅当无祖先且无后代时附加到当前行的 assistant 内容上）
        if node in INSERT_NODES and pressure_idx < len(pressure_list):
            # 无祖先和无后代
            if len(ancestors) == 0 and len(descendant_chain) == 0:
                if random.random() < 0.7:
                    # 修改 turn_list 中最后一个元素（当前行）的 assistant_text
                    last_idx = len(turn_list) - 1
                    current_user, current_assist = turn_list[last_idx]
                    new_assist = current_assist + pressure_list[pressure_idx]
                    turn_list[last_idx] = (current_user, new_assist)
                    pressure_idx += 1

        # 将所有轮次加入 messages
        for user_txt, assistant_txt in turn_list:
            if user_txt:
                messages.append({"role": "user", "content": user_txt})
            if assistant_txt:
                messages.append({"role": "assistant", "content": assistant_txt})

    return messages

def main():
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    print(f"随机种子: {RANDOM_SEED}")

    # 加载数据
    print("加载 Excel 模块...")
    df_dict = load_sheets(EXCEL_PATH)
    print("加载概率矩阵...")
    prob_df = load_prob_matrix(PROB_PATH, MODULES)
    # 路径缓存文件
    PATHS_CACHE = "intermediate/all_paths.json"
    os.makedirs(os.path.dirname(PATHS_CACHE), exist_ok=True)

    # 加载案例列表
    case_files = sorted([f for f in os.listdir(CASES_DIR) if f.endswith('.txt')])
    cases = []
    prompts = []
    for fname in case_files:
        path = os.path.join(CASES_DIR, fname)
        cases.append(parse_case_info(path))
        prompts.append(get_full_prompt(path))
    print(f"加载案例数量: {len(cases)}")

    # 生成路径（带缓存校验）
    print(f"生成 {NUM_PATHS} 条路径...")
    cache_valid = False
    all_paths = None

    if os.path.exists(PATHS_CACHE):
        with open(PATHS_CACHE, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        # 校验种子和路径数量
        if cache_data.get("seed") == RANDOM_SEED and cache_data.get("num_paths") == NUM_PATHS:
            all_paths = cache_data["paths"]
            cache_valid = True
            print(f"从缓存加载路径成功，共 {len(all_paths)} 条（种子: {RANDOM_SEED}）")
        else:
            print(f"缓存文件中的种子或路径数量不匹配，将重新生成路径")
            print(f"  缓存种子: {cache_data.get('seed')}, 当前种子: {RANDOM_SEED}")
            print(f"  缓存数量: {cache_data.get('num_paths')}, 当前数量: {NUM_PATHS}")

    if not cache_valid:
        # 重新生成路径
        all_paths = []
        for _ in range(NUM_PATHS):
            path = ["核实"]
            counts = {mod: 0 for mod in MODULES}
            counts["核实"] = 1
            banned = set()
            current = "核实"
            while True:
                probs = prob_df.loc[current].copy()
                available = [m for m in MODULES if m not in banned]
                if not available:
                    break
                probs = probs[available]
                if probs.sum() == 0:
                    break
                probs /= probs.sum()
                next_node = np.random.choice(available, p=probs)
                path.append(next_node)
                counts[next_node] += 1
                max_repeat = MAX_REPEAT.get(next_node, 100)
                if counts[next_node] >= max_repeat:
                    if next_node in SPECIAL_NODES:
                        banned.add(next_node)
                    else:
                        break
                current = next_node
            all_paths.append(path)

        # 保存到缓存（包含种子和数量）
        cache_data = {
            "seed": RANDOM_SEED,
            "num_paths": NUM_PATHS,
            "paths": all_paths
        }
        with open(PATHS_CACHE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        print(f"路径生成完成，共 {len(all_paths)} 条，已保存至 {PATHS_CACHE}（种子: {RANDOM_SEED}）")

    # 生成对话
    print("开始生成对话...")
    all_dialogues = []
    case_idx = 0
    for i, path in enumerate(all_paths):
        case = cases[case_idx % len(cases)]
        prompt = prompts[case_idx % len(prompts)]
        case_idx += 1
        try:
            messages = generate_dialogue(path, df_dict, case, prompt)
            # ---------- 关键修改：替换所有消息中的占位符 ----------
            for msg in messages:
                if 'content' in msg:
                    msg['content'] = fill_placeholders(msg['content'], case)
            all_dialogues.append({"messages": messages})
        except Exception as e:
            import traceback
            print(f"生成第{i}条对话时出错，路径长度: {len(path)}, 案例索引: {case_idx-1}")
            traceback.print_exc()
            continue
        if (i+1) % 5000 == 0:
            print(f"已生成 {i+1}/{NUM_PATHS} 条对话")

    # 保存结果
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(OUTPUT_DIR, f"yangqian_dialogues_{timestamp}.json")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(all_dialogues, f, ensure_ascii=False, indent=2)
    print(f"生成完成，共 {len(all_dialogues)} 条对话，保存至 {out_file}")

if __name__ == "__main__":
    main()