'''
Step 9：重构主流程
操作：创建新的 main.py：

加载配置

初始化数据加载器，加载 Excel、概率矩阵、案例

初始化条件解析器（可配置选择哪种实现）

初始化路径生成器，生成或缓存路径

初始化对话构建器，遍历路径和案例生成对话

保存 JSON 输出
原因：主流程只负责编排，不包含具体业务逻辑，清晰直观。
'''


#!/usr/bin/env python3
"""
多轮对话生成脚本（重构版）
基于配置驱动、模块化设计，支持通用催收模板。
"""

import os
import json
from datetime import datetime
from core.config import load_config
from core.logger import init_logger, get_logger
from core.data_loader import load_sheets, load_prob_matrix, load_cases
from core.path_generator import PathGenerator
from core.dialogue_builder import DialogueBuilder
from core.factory import create_condition_evaluator

def main():
    # 1. 加载配置
    config_path = "configs/general.yaml"
    config = load_config(config_path)
    # 初始化日志
    init_logger(config)
    logger = get_logger()

    logger.info("=== 对话生成系统启动 ===")
    logger.info(f"配置文件: {config_path}")

    # 2. 加载数据
    logger.info("加载 Excel 模块...")
    excel_path = config.get('excel_path')
    modules = config.get('modules')
    df_dict = load_sheets(excel_path, modules, condition_keyword='逾期')

    logger.info("加载概率矩阵...")
    prob_path = config.get('prob_path')
    prob_df = load_prob_matrix(prob_path, modules)

    logger.info("加载案例...")
    cases_dir = config.get('cases_dir')
    cases, prompts = load_cases(cases_dir)
    logger.info(f"加载案例数量: {len(cases)}")

    # 3. 创建条件解析器
    condition_evaluator = create_condition_evaluator(config)

    # 4. 生成路径
    path_gen = PathGenerator(config, prob_df)
    num_paths = config.get('num_paths')
    seed = config.get('random_seed')
    cache_path = config.get('paths_cache')
    logger.info(f"开始生成 {num_paths} 条路径...")
    all_paths = path_gen.generate(num_paths, seed, cache_path)
    logger.info(f"路径生成完成，共 {len(all_paths)} 条")

    # 5. 构建对话
    builder = DialogueBuilder(config, df_dict, condition_evaluator)
    all_dialogues = []
    case_idx = 0

    logger.info("开始生成对话...")
    for i, path in enumerate(all_paths):
        case = cases[case_idx % len(cases)]
        prompt = prompts[case_idx % len(prompts)]
        case_idx += 1
        try:
            messages = builder.build(path, case, prompt)
            all_dialogues.append({"messages": messages})
        except Exception as e:
            logger.error(f"生成第{i}条对话时出错，路径长度: {len(path)}", exc_info=True)
            continue
        if (i+1) % 5000 == 0:
            logger.info(f"已生成 {i+1}/{len(all_paths)} 条对话")

    # 6. 保存结果
    output_dir = config.get('output_dir', 'output')
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(output_dir, f"general_dialogues_{timestamp}.json")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(all_dialogues, f, ensure_ascii=False, indent=2)
    logger.info(f"生成完成，共 {len(all_dialogues)} 条对话，保存至 {out_file}")

if __name__ == "__main__":
    main()