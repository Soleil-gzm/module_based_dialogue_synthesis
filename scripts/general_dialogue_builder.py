#!/usr/bin/env python3
"""
多轮对话生成脚本（通用电催话术模板）
基于 Excel 模块和概率矩阵，按照业务规则生成对话路径并采样话术。
支持自循环模块（A集）、循环模块（B集）、终止模块等特殊规则。
"""

import json
import logging
import os
import random
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ========== 日志配置 ==========
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
log_filename = os.path.join(
    LOG_DIR, f"dialogue_builder_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ========== 配置参数 ==========
EXCEL_PATH = "datas/【生成式通用】电催话术通用模板-首催 - 20260330.xlsx"
PROB_PATH = "datas/prob.xlsx"
CASES_DIR = "datas/cases"
OUTPUT_DIR = "output"
NUM_PATHS = 40000  # 生成对话数量
RANDOM_SEED = 42  # 随机种子
PATHS_CACHE = "intermediate/all_paths.json"  # 路径缓存文件

# 模块列表（与 Excel 中的 sheet 名称一致）
MODULES = [
    "身份确认",
    "告知",
    "信息核实",
    "三方",
    "转告",
    "承诺还款",
    "已还款",
    "敷衍",
    "投诉处理",
    "信息问题",
    "不方便接电",
    "对抗",
    "没钱",
    "诉求",
    "通用原因",
    "否认办理业务",
    "工程款",
    "未发工资",
    "还错卡",
    "生病住院",
    "破产",
    "失业",
    "他人用款",
    "忘记还款",
    "盗刷",
]

# 自循环模块集（A集）
A_SET = {
    "通用原因",
    "否认办理业务",
    "工程款",
    "未发工资",
    "还错卡",
    "生病住院",
    "破产",
    "失业",
    "他人用款",
    "忘记还款",
    "盗刷",
}

# 循环模块集（B集）
B_SET = {
    "敷衍",
    "投诉处理",
    "信息问题",
    "不方便接电",
    "对抗",
    "没钱",
    "诉求",
    "承诺还款",
}

# 终止模块（进入后路径结束）
TERMINAL_NODES = {"承诺还款", "已还款"}

# 每个模块的最大重复次数
MAX_REPEAT = {
    "身份确认": 4,
    "告知": 1,
    "信息核实": 1,
    "三方": 1,
    "转告": 1,
    "承诺还款": 2,
    "已还款": 1,
    "敷衍": 3,
    "投诉处理": 3,
    "信息问题": 3,
    "不方便接电": 2,
    "对抗": 4,
    "没钱": 4,
    "诉求": 3,
    "通用原因": 4,
    "否认办理业务": 4,
    "工程款": 4,
    "未发工资": 4,
    "还错卡": 4,
    "生病住院": 4,
    "破产": 4,
    "失业": 4,
    "他人用款": 4,
    "忘记还款": 4,
    "盗刷": 4,
}

# 可以附加衔接施压话术的模块（触发概率60%）
INSERT_NODES = {"失业", "破产", "生病住院", "未发工资", "工程款", "通用原因", "没钱"}
PRESSURE_PROB = 0.6

# 特殊模块：达到最大次数后仅禁用，不终止对话（只有信息问题）
# SPECIAL_NODES = {'信息问题'}


# ========== 辅助函数 ==========
def load_sheets(excel_path):
    """加载所有工作表，保留 conditions 包含 '逾期' 的行，存储到 df_dict"""
    df_dict = {}
    for sheet in MODULES:
        df = pd.read_excel(excel_path, sheet_name=sheet)
        # 筛选 conditions 列包含 '逾期' 的行
        mask = df["conditions(条件)"].apply(
            lambda x: isinstance(x, str) and "逾期" in x
        )
        df_filtered = df[mask].copy()
        # 去掉 human 列中包含随机标签的行（原始逻辑）
        df_filtered = df_filtered[
            ~df_filtered["human(客户)"].str.contains("{随机金额}|{随机时间}", na=False)
        ]
        df_dict[sheet] = df_filtered
    return df_dict


def load_prob_matrix(prob_path, modules):
    """加载概率矩阵，第一行和第一列为模块名"""
    prob_df = pd.read_excel(prob_path, header=0, index_col=0)
    # 确保行列顺序与 modules 一致
    prob_df = prob_df.reindex(index=modules, columns=modules)
    prob_df = prob_df / 100.0
    return prob_df


def parse_case_info(txt_path):
    """解析通用案例文件，返回字段字典"""
    data = {}
    with open(txt_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines:
        line = line.strip()
        if line.startswith("- 客服电话："):
            data["客服电话"] = line.split("：")[1].strip()
        elif line.startswith("- 机构名称："):
            data["机构名称"] = line.split("：")[1].strip()
        elif line.startswith("- 业务类型："):
            data["业务类型"] = line.split("：")[1].strip()
        elif line.startswith("- APP名称："):
            data["APP名称"] = line.split("：")[1].strip()
        elif line.startswith("- 抬头："):
            data["抬头"] = line.split("：")[1].strip()
        elif line.startswith("- 专员工号："):
            data["专员工号"] = line.split("：")[1].strip()
        elif line.startswith("- 姓名："):
            data["客户姓名"] = line.split("：")[1].strip()
        elif line.startswith("- 性别："):
            data["客户性别"] = line.split("：")[1].strip()
        elif line.startswith("- 逾期天数："):
            data["逾期天数"] = line.split("：")[1].strip()
        elif line.startswith("- 今天日期："):
            data["今天日期"] = line.split("：")[1].strip()
        elif line.startswith("- 查账时间："):
            data["查账时间"] = line.split("：")[1].strip()
        elif line.startswith("- 还款日："):
            data["还款日"] = line.split("：")[1].strip()
        elif line.startswith("- 逾期金额："):
            data["逾期金额"] = line.split("：")[1].strip()
        elif line.startswith("- 总欠款："):
            data["总欠款"] = line.split("：")[1].strip()
        elif line.startswith("- 本金："):
            data["本金"] = line.split("：")[1].strip()
    # 生成随机金额：逾期金额的 30%~70%
    data["随机金额"] = str(round(float(data["逾期金额"]) * random.uniform(0.3, 0.7)))
    # 随机时间：查账时间加上1~4小时（简单处理，直接拼接）
    data["随机时间"] = f"{data['查账时间']}过后{random.randint(1,4)}小时"
    # 随机数字
    data["随机数字"] = str(random.randint(100, 999))
    return data


def get_full_prompt(txt_path):
    """读取整个 case 文件内容作为 system prompt 的后半部分"""
    with open(txt_path, "r", encoding="utf-8") as f:
        return f.read()


def get_ancestors(uid, df):
    """递归获取所有祖先行（按从远祖到父的顺序）"""
    ancestors = []
    while True:
        parent_series = df.loc[df["uid"] == uid, "parent(继承)"]
        if parent_series.empty:
            break
        parent_val = parent_series.values[0]
        if pd.isna(parent_val) or parent_val == 0:
            break
        parent_row = df[df["uid"] == parent_val]
        if parent_row.empty:
            break
        ancestors.append(parent_row.iloc[0])
        uid = parent_val
    return list(reversed(ancestors))


def get_random_descendant_chain(uid, df, stop_prob=0.3, max_depth=10):
    """递归获取一条随机的后代链（考虑 flexible_stop）"""
    children = df[df["parent(继承)"] == uid]
    if children.empty or max_depth <= 0:
        return []
    child_row = children.sample(n=1).iloc[0]
    chain = [child_row]
    flex_stop = child_row.get("flexible_stop(可选不继承)", 0)
    if pd.notna(flex_stop) and flex_stop == 1 and random.random() < stop_prob:
        return chain
    deeper = get_random_descendant_chain(child_row["uid"], df, stop_prob, max_depth - 1)
    chain.extend(deeper)
    return chain


def matches_conditions(row, case):
    """检查 row 的 conditions(条件) 是否与当前 case 匹配"""
    cond_str = row.get("conditions(条件)", "")
    if pd.isna(cond_str) or cond_str == "":
        return True
    # 简化为只要包含 '逾期' 即通过（所有预过滤的行都满足）
    if "逾期" in cond_str:
        return True
    return True


def sample_utterance(row, is_human):
    """从一行中随机抽取一个话术（用 / 分割）"""
    col = "human(客户)" if is_human else "assistant(专员)"
    text = row[col]
    if pd.isna(text):
        return ""
    options = [s.strip() for s in str(text).split("/") if s.strip()]
    if not options:
        return ""
    return random.choice(options)


def fill_placeholders(text, case):
    """替换文本中的花括号占位符"""
    if not isinstance(text, str):
        return text
    replacements = {
        "{客服电话}": case.get("客服电话", ""),
        "{机构名称}": case.get("机构名称", ""),
        "{业务类型}": case.get("业务类型", ""),
        "{APP名称}": case.get("APP名称", ""),
        "{抬头}": case.get("抬头", ""),
        "{专员工号}": case.get("专员工号", ""),
        "{客户姓名}": case.get("客户姓名", ""),
        "{客户性别}": case.get("客户性别", ""),
        "{逾期天数}": str(case.get("逾期天数", "")),
        "{今天日期}": case.get("今天日期", ""),
        "{查账时间}": case.get("查账时间", ""),
        "{逾期金额}": case.get("逾期金额", ""),
        "{总欠款}": case.get("总欠款", ""),
        "{本金}": case.get("本金", ""),
        "{还款日}": case.get("还款日", ""),
        "{随机金额}": case.get("随机金额", ""),
        "{随机时间}": case.get("随机时间", ""),
        "{随机数字}": case.get("随机数字", ""),
        "{empty_tag}": "",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text


def generate_path(prob_df, modules, max_repeat, terminal_nodes, a_set, b_set):
    """
    按照业务规则生成一条模块序列路径
    - 只有 terminal_nodes 中的模块（承诺还款、已还款）会终止路径
    - 其他模块达到 max_repeat 后仅被禁用（不再进入），路径继续
    - 当所有可能候选模块都被禁用或无可转移时，路径自然结束
    """
    path = ["身份确认"]
    counts = {mod: 0 for mod in modules}
    counts["身份确认"] = 1
    banned = set()
    selected_a = None  # 记录当前路径中出现的自循环模块（只能有一个）
    current = "身份确认"

    while True:
        # 1. 根据当前节点类型确定合法下一节点候选集
        if current == "身份确认":
            candidates = ["告知", "三方"]
        elif current == "告知":
            # 告知不能转身份确认和转告
            candidates = [m for m in modules if m not in ["身份确认", "转告"]]
        elif current == "信息核实":
            # 信息核实不能转告知、身份确认、三方、转告
            candidates = [
                m for m in modules if m not in ["告知", "身份确认", "三方", "转告"]
            ]
        elif current in a_set:
            # 自循环模块（A集）：允许自身 + B集
            candidates = [current] + list(b_set)
        elif current in b_set:
            # 循环模块（B集）：允许 B集 + 如果已有选中的A，则允许返回那个A
            candidates = list(b_set)
            if selected_a is not None:
                candidates.append(selected_a)
        else:
            # 其他模块（如三方、转告）按照全量模块（但排除已禁用的）
            candidates = modules[:]

        # 2. 移除已禁用的模块（达到最大次数）
        candidates = [m for m in candidates if m not in banned]

        # 3. 如果已经选中了一个自循环模块，则禁止选择其他自循环模块
        if selected_a is not None:
            candidates = [m for m in candidates if m not in a_set or m == selected_a]

        if not candidates:
            break

        # 4. 获取当前节点的概率向量，并过滤到候选集
        probs = prob_df.loc[current].copy()
        probs = probs[probs.index.isin(candidates)]
        if probs.sum() == 0:
            break
        probs /= probs.sum()

        # 5. 随机选择下一模块
        next_node = np.random.choice(probs.index, p=probs)

        # 6. 硬约束：已还款只能从告知或信息核实进入
        if next_node == "已还款" and current not in ["告知", "信息核实"]:
            continue

        # 7. 如果本次选择了自循环模块，且当前还没有记录 selected_a，则记录
        if next_node in a_set and selected_a is None:
            selected_a = next_node

        # 8. 加入路径，更新计数
        path.append(next_node)
        counts[next_node] += 1

        # 9. 检查是否达到最大重复次数
        max_repeat_val = max_repeat.get(next_node, 100)
        if counts[next_node] >= max_repeat_val:
            banned.add(next_node)  # 达标后禁用，但不终止路径（除非是终止模块）

        # 10. 只有终止模块才结束路径
        if next_node in terminal_nodes:
            break

        # 11. 继续
        current = next_node

    return path


def generate_dialogue(path, df_dict, case, prompt_text):
    """根据一条模块路径和一个案例，生成完整对话 messages"""
    messages = []
    sys_content = (
        f"你是一个{case.get('抬头', '催收专员')}，请根据客户的情况，使用合适的话术与客户进行沟通，争取让客户承诺还款。\n"
        + prompt_text
    )
    messages.append({"role": "system", "content": sys_content})

    node_counts = {}
    # 加载衔接施压话术（三个备选）
    pressure_df = df_dict.get("链接施压话术", pd.DataFrame())
    pressure_list = []
    for repeat in [1, 2, 3]:
        if not pressure_df.empty:
            sub = pressure_df[
                pressure_df["repeat(次数)"].apply(
                    lambda x: str(repeat) in str(x).split("/") if pd.notna(x) else False
                )
            ]
            if not sub.empty:
                row = sub.sample(n=1).iloc[0]
                assistant_opt = row["assistant(专员)"]
                if pd.notna(assistant_opt):
                    opt_list = [
                        s.strip() for s in assistant_opt.split("/") if s.strip()
                    ]
                    if opt_list:
                        pressure_list.append(random.choice(opt_list))
                    else:
                        pressure_list.append("")
                else:
                    pressure_list.append("")
            else:
                pressure_list.append("")
        else:
            pressure_list.append("")
    pressure_idx = 0

    for node in path:
        node_counts[node] = node_counts.get(node, 0) + 1
        repeat = node_counts[node]
        df_node = df_dict[node]

        # 筛选符合条件的行：repeat 次数匹配
        mask = df_node["repeat(次数)"].apply(
            lambda x: str(repeat) in str(x).split("/") if pd.notna(x) else False
        )
        candidates = df_node[mask]
        if candidates.empty:
            logger.debug(f"模块 {node}, repeat={repeat}: 无候选行")
            continue

        valid_rows = [
            row for _, row in candidates.iterrows() if matches_conditions(row, case)
        ]
        if not valid_rows:
            logger.debug(f"模块 {node}, repeat={repeat}: 无候选行（条件不匹配）")
            continue
        row = random.choice(valid_rows)

        # 处理继承链：祖先 + 当前 + 后代
        turn_list = []
        ancestors = get_ancestors(row["uid"], df_node)
        for anc in ancestors:
            user_text = sample_utterance(anc, True)
            assistant_text = sample_utterance(anc, False)
            if user_text or assistant_text:
                turn_list.append((user_text, assistant_text))

        current_user = sample_utterance(row, True)
        current_assistant = sample_utterance(row, False)

        descendant_chain = get_random_descendant_chain(row["uid"], df_node)

        # 附加衔接施压话术（仅当无祖先且无后代时）
        attached_pressure = False
        if node in INSERT_NODES and pressure_idx < len(pressure_list):
            if len(ancestors) == 0 and len(descendant_chain) == 0:
                if random.random() < PRESSURE_PROB:
                    current_assistant += pressure_list[pressure_idx]
                    pressure_idx += 1
                    attached_pressure = True

        turn_list.append((current_user, current_assistant))
        for desc in descendant_chain:
            user_text = sample_utterance(desc, True)
            assistant_text = sample_utterance(desc, False)
            if user_text or assistant_text:
                turn_list.append((user_text, assistant_text))

        # 添加消息
        for user_txt, assistant_txt in turn_list:
            if user_txt:
                messages.append({"role": "user", "content": user_txt})
            if assistant_txt:
                messages.append({"role": "assistant", "content": assistant_txt})

        # 检查是否再见：如果当前行 '是否再见' == 1 且 repeat < MAX_REPEAT[node]，终止对话
        max_repeat_val = MAX_REPEAT.get(node, 999)
        if row.get("是否再见") == 1 and repeat < max_repeat_val:
            logger.debug(f"模块 {node} repeat={repeat} 遇到是否再见=1，提前终止对话")
            break

    return messages


def main():
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    logger.info(f"随机种子: {RANDOM_SEED}")

    # 加载数据
    logger.info("加载 Excel 模块...")
    df_dict = load_sheets(EXCEL_PATH)
    logger.info("加载概率矩阵...")
    prob_df = load_prob_matrix(PROB_PATH, MODULES)

    # 加载案例列表
    case_files = sorted([f for f in os.listdir(CASES_DIR) if f.endswith(".txt")])
    cases = []
    prompts = []
    for fname in case_files:
        path = os.path.join(CASES_DIR, fname)
        cases.append(parse_case_info(path))
        prompts.append(get_full_prompt(path))
    logger.info(f"加载案例数量: {len(cases)}")

    # 生成或加载路径
    os.makedirs(os.path.dirname(PATHS_CACHE), exist_ok=True)
    need_generate = True
    all_paths = None
    if os.path.exists(PATHS_CACHE):
        with open(PATHS_CACHE, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
        if isinstance(cache_data, list):
            logger.info("检测到旧格式缓存，重新生成路径...")
        else:
            if (
                cache_data.get("seed") == RANDOM_SEED
                and cache_data.get("num_paths") == NUM_PATHS
            ):
                all_paths = cache_data["paths"]
                logger.info(f"从缓存加载路径成功，共 {len(all_paths)} 条")
                need_generate = False
            else:
                logger.info("缓存种子或数量不匹配，重新生成路径...")

    # 强制生成不重复的路径（直到达到目标数量或最大尝试次数）
    if need_generate:
        logger.info(f"生成 {NUM_PATHS} 条不重复路径...")
        all_paths = []
        max_attempts = NUM_PATHS * 10  # 防止无限循环
        attempts = 0
        paths_set = set()

        while len(all_paths) < NUM_PATHS and attempts < max_attempts:
            attempts += 1
            path = generate_path(
                prob_df, MODULES, MAX_REPEAT, TERMINAL_NODES, A_SET, B_SET
            )
            # 将路径转为元组以便存入 set
            path_tuple = tuple(path)
            if path_tuple not in paths_set:
                paths_set.add(path_tuple)
                all_paths.append(path)
            if attempts % 10000 == 0:
                logger.info(f"已尝试 {attempts} 次，当前唯一路径数 {len(all_paths)}")

        if len(all_paths) < NUM_PATHS:
            logger.warning(
                f"仅生成 {len(all_paths)} 条不重复路径，达到最大尝试次数 {max_attempts}。"
            )
        else:
            logger.info(f"成功生成 {len(all_paths)} 条不重复路径。")

        # 保存缓存
        cache_data = {"seed": RANDOM_SEED, "num_paths": NUM_PATHS, "paths": all_paths}
        with open(PATHS_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        logger.info(f"路径生成完成，共 {len(all_paths)} 条，已保存至 {PATHS_CACHE}")

    # 生成对话
    logger.info("开始生成对话...")
    all_dialogues = []
    case_idx = 0
    for i, path in enumerate(all_paths):
        case = cases[case_idx % len(cases)]
        prompt = prompts[case_idx % len(prompts)]
        case_idx += 1
        try:
            messages = generate_dialogue(path, df_dict, case, prompt)
            for msg in messages:
                if "content" in msg:
                    msg["content"] = fill_placeholders(msg["content"], case)
            all_dialogues.append({"messages": messages})
        except Exception as e:
            import traceback

            logger.error(
                f"生成第{i}条对话时出错，路径长度: {len(path)}, 案例索引: {case_idx-1}"
            )
            logger.error(traceback.format_exc())
            continue
        if (i + 1) % 5000 == 0:
            logger.info(f"已生成 {i+1}/{NUM_PATHS} 条对话")

    # 保存结果
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(OUTPUT_DIR, f"general_dialogues_{timestamp}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_dialogues, f, ensure_ascii=False, indent=2)
    logger.info(f"生成完成，共 {len(all_dialogues)} 条对话，保存至 {out_file}")


if __name__ == "__main__":
    main()
