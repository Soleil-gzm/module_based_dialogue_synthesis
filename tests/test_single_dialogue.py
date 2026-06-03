#!/usr/bin/env python3
"""
测试脚本：详细打印单条路径生成和对话生成的过程
用于理解 PathGenerator 和 DialogueBuilder 的内部逻辑
"""

import sys
import os

# 添加项目根目录到路径，以便导入 core 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from core.config import load_config
from core.random_service import RandomService
from core.data_loader import load_sheets, load_prob_matrix, load_cases
from core.condition import KeywordConditionEvaluator
from core.path_generator import PathGenerator
from core.dialogue_builder import DialogueBuilder
from core.utterance import sample_utterance, get_ancestors, get_random_descendant_chain


def print_section(title):
    """打印分节标题"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def test_single_path_and_dialogue():
    # 加载配置
    config_path = "configs/general.yaml"
    config = load_config(config_path)
    seed = config.get('random_seed', 42)
    rng = RandomService(seed)
    print(f"随机种子: {seed}")

    # 加载数据
    print("加载 Excel 模块...")
    excel_path = config.get('excel_path')
    modules = config.get('modules')
    df_dict = load_sheets(excel_path, modules, condition_keyword='逾期')

    print("加载概率矩阵...")
    prob_path = config.get('prob_path')
    prob_df = load_prob_matrix(prob_path, modules)

    print("加载案例...")
    cases_dir = config.get('cases_dir')
    cases, prompts = load_cases(cases_dir, rng)   # 注意：需要修改 load_cases 以接收 rng，或者先不用 rng
    case = cases[0]
    prompt = prompts[0]
    print(f"使用案例: {case.get('客户姓名', '未知')}, 逾期天数: {case.get('逾期天数', '未知')}\n")

    # 创建条件解析器
    condition_evaluator = KeywordConditionEvaluator()

    # ---------------------- 路径生成（详细打印） ----------------------
    print_section("一、路径生成过程（模拟 generate_one 内部逻辑）")

    # 手动模拟路径生成，加入详细打印
    path = [config.get('start_module', modules[0])]
    print(f"初始模块: {path[0]}\n")

    counts = {mod: 0 for mod in modules}
    counts[path[0]] = 1
    banned = set()
    selected_a = None
    current = path[0]

    max_repeat = config.get('max_repeat')
    terminal_nodes = set(config.get('terminal_modules', []))
    a_set = set(config.get('a_set', []))
    b_set = set(config.get('b_set', []))

    step = 1
    while True:
        print(f"--- 步骤 {step} ---")
        print(f"当前模块: {current}")
        print(f"已禁用模块: {banned if banned else '无'}")
        print(f"已选中的A集: {selected_a if selected_a else '未选中'}")
        print(f"各模块已出现次数: { {k: v for k, v in counts.items() if v > 0} }")

        # 确定候选集
        if current == "身份确认":
            candidates = ["告知", "三方"]
            print(f"规则: current='身份确认' → 候选集 = {candidates}")
        elif current == "告知":
            candidates = [m for m in modules if m not in ["身份确认", "转告"]]
            print(f"规则: current='告知' → 排除['身份确认','转告']，候选集 = {candidates}")
        elif current == "信息核实":
            candidates = [m for m in modules if m not in ["告知", "身份确认", "三方", "转告"]]
            print(f"规则: current='信息核实' → 排除['告知','身份确认','三方','转告']，候选集 = {candidates}")
        elif current in a_set:
            candidates = [current] + list(b_set)
            print(f"规则: current在A集({current}) → 候选集 = 自身 + B集 = {candidates}")
        elif current in b_set:
            candidates = list(b_set)
            if selected_a is not None:
                candidates.append(selected_a)
            print(f"规则: current在B集({current}) → 候选集 = B集" + (f" + 已选A集({selected_a})" if selected_a else "") + f" = {candidates}")
        else:
            candidates = modules[:]
            print(f"规则: 其他模块 → 全模块候选集 = {candidates}")

        # 过滤banned
        before_filter = candidates[:]
        candidates = [m for m in candidates if m not in banned]
        if before_filter != candidates:
            print(f"移除banned模块后: {candidates}")

        # 过滤其他A集（如果已选中一个A）
        if selected_a is not None:
            before_a = candidates[:]
            candidates = [m for m in candidates if m not in a_set or m == selected_a]
            if before_a != candidates:
                print(f"已选中A集({selected_a})，禁止其他A集，候选集变为: {candidates}")

        if not candidates:
            print("候选集为空，终止路径生成\n")
            break

        # 获取概率
        probs = prob_df.loc[current].copy()
        probs = probs[probs.index.isin(candidates)]
        if probs.sum() == 0:
            print("概率和为0，终止路径生成\n")
            break
        probs /= probs.sum()
        print("归一化后的转移概率:")
        for mod, p in probs.items():
            print(f"  {mod}: {p:.3f}")

        # 随机选择下一个模块
        next_node = rng.np_choice(probs.index.to_numpy(), p=probs.to_numpy())
        print(f"随机选中下一个模块: {next_node}")

        # 特殊约束：已还款只能从告知或信息核实进入
        if next_node == "已还款" and current not in ["告知", "信息核实"]:
            print(f"违反约束: {next_node} 只能从'告知'或'信息核实'进入，当前是 {current}，重新选择")
            continue

        # 记录A集
        if next_node in a_set and selected_a is None:
            selected_a = next_node
            print(f"第一次遇到A集模块 {next_node}，记录为selected_a")

        path.append(next_node)
        counts[next_node] += 1
        print(f"路径更新: {path}")

        # 检查重复次数限制
        max_repeat_val = max_repeat.get(next_node, 100)
        if counts[next_node] >= max_repeat_val:
            banned.add(next_node)
            print(f"模块 {next_node} 已达最大重复次数 {max_repeat_val}，加入禁用集")

        # 终止检查
        if next_node in terminal_nodes:
            print(f"遇到终止模块 {next_node}，路径生成结束")
            break

        current = next_node
        step += 1
        print()

    print_section("生成的最终路径")
    print(" -> ".join(path))

    # ---------------------- 对话生成（详细打印） ----------------------
    print_section("二、基于上述路径的对话生成过程")
    print(f"使用案例: {case}")
    print()

    # 创建对话构建器（使用真实类，但重写部分方法以捕获内部细节不现实，我们直接模拟其主要逻辑）
    # 为了方便观察，我们将核心逻辑展开打印
    builder = DialogueBuilder(config, df_dict, condition_evaluator, rng, None)

    messages = []
    sys_content = f"你是一个{case.get('抬头', '催收专员')}，请根据客户的情况，使用合适的话术与客户进行沟通，争取让客户承诺还款。\n{prompt}"
    messages.append({"role": "system", "content": sys_content})
    print(f"[System] {sys_content[:200]}...\n")

    node_counts = {}
    builder.pressure_manager.reset()

    for idx, node in enumerate(path):
        print(f"--- 处理模块 {idx+1}/{len(path)}: {node} ---")
        node_counts[node] = node_counts.get(node, 0) + 1
        repeat = node_counts[node]
        df_node = df_dict.get(node)
        if df_node is None or df_node.empty:
            print(f"  模块 {node} 无数据，跳过")
            continue

        print(f"  当前重复次数: {repeat}")
        print(f"  从 DataFrame 中筛选 repeat(次数) 包含 {repeat} 的行...")
        mask = df_node['repeat(次数)'].apply(
            lambda x: str(repeat) in str(x).split('/') if pd.notna(x) else False)
        candidates = df_node[mask]
        if candidates.empty:
            print("  无候选行，跳过")
            continue

        print(f"  候选行数: {len(candidates)}")
        # 条件筛选
        valid_rows = []
        for _, row in candidates.iterrows():
            cond_str = row.get('conditions(条件)', '')
            if condition_evaluator.evaluate(cond_str, case):
                valid_rows.append(row)
        if not valid_rows:
            print("  无满足条件的行，跳过")
            continue

        print(f"  满足条件的行数: {len(valid_rows)}")
        row = rng.choice(valid_rows)
        print(f"  选中行 uid={row['uid']}, conditions={row.get('conditions(条件)', '')}")

        # 获取祖先和后代链（直接调用独立函数）
        ancestors = get_ancestors(row['uid'], df_node)
        descendant_chain = get_random_descendant_chain(row['uid'], df_node, rng)

        print(f"  祖先数量: {len(ancestors)}")
        for i, anc in enumerate(ancestors):
            print(f"    祖先{i+1}: uid={anc['uid']}")
        print(f"  后代链长度: {len(descendant_chain)}")
        for i, desc in enumerate(descendant_chain):
            print(f"    后代{i+1}: uid={desc['uid']}")

        # 抽取话术（调用独立函数）
        turn_list = []
        for anc in ancestors:
            user_txt = sample_utterance(anc, True, rng)
            assistant_txt = sample_utterance(anc, False, rng)
            if user_txt or assistant_txt:
                turn_list.append((user_txt, assistant_txt))

        current_user = sample_utterance(row, True, rng)
        current_assistant = sample_utterance(row, False, rng)

        # 施压话术附加
        inserted = False
        if node in builder.insert_nodes and len(ancestors) == 0 and len(descendant_chain) == 0:
            if rng.random() < builder.pressure_prob:
                pressure_text = builder.pressure_manager.get_next_pressure()
                if pressure_text:
                    current_assistant += pressure_text
                    inserted = True

        turn_list.append((current_user, current_assistant))
        for desc in descendant_chain:
            user_txt = sample_utterance(desc, True, rng)
            assistant_txt = sample_utterance(desc, False, rng)
            if user_txt or assistant_txt:
                turn_list.append((user_txt, assistant_txt))

        # 打印本轮抽取的话术对
        print("  生成的话术对（按顺序）:")
        for i, (u, a) in enumerate(turn_list):
            print(f"    轮次{i+1}:")
            if u:
                print(f"      客户: {u}")
            if a:
                print(f"      专员: {a}")
        if inserted:
            print("    [注] 专员话术后附带了施压话术")

        # 检查是否再见
        if row.get('是否再见') == 1 and repeat < builder.max_repeat.get(node, 999):
            print("  遇到'是否再见'标志，提前终止对话")
            break
        print()

    print_section("对话生成完毕（仅展示了结构，实际 message 列表已构建）")


if __name__ == "__main__":
    test_single_path_and_dialogue()