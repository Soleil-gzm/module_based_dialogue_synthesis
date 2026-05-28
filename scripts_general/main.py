#!/usr/bin/env python3
"""
多轮对话生成脚本（重构版）
基于配置驱动、模块化设计，支持通用催收模板。
"""

import os
import json
import pickle  # 用于保存检查点状态
from datetime import datetime
from core.config import load_config
from core.logger import init_logger, get_logger
from core.data_loader import load_sheets, load_prob_matrix, load_cases
from core.path_generator import PathGenerator
from core.dialogue_builder import DialogueBuilder
from core.factory import create_condition_evaluator
from core.random_service import RandomService

def save_checkpoint(dialogues: list, next_index: int, checkpoint_file: str):
    """保存对话生成进度"""
    with open(checkpoint_file, 'w', encoding='utf-8') as f:
        json.dump({
            "next_index": next_index,
            "dialogues": dialogues
        }, f, ensure_ascii=False, indent=2)

def load_checkpoint(checkpoint_file: str):
    """加载检查点，返回 (dialogues, next_index)"""
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get("dialogues", []), data.get("next_index", 0)
    return [], 0

def main():
    # 1. 加载配置
    config_path = "configs/general.yaml"
    config = load_config(config_path)
    # 初始化日志
    init_logger(config)
    logger = get_logger()

    logger.info("=== 对话生成系统启动 ===")
    logger.info(f"配置文件: {config_path}")

    # 2. 随机服务（使用配置中的随机种子）
    seed = config.get('random_seed', 42)
    rng = RandomService(seed)
    logger.info(f"随机种子: {seed}")

    # 3. 加载数据
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

    # 4. 创建条件解析器
    condition_evaluator = create_condition_evaluator(config)

    # 5. 生成路径（带缓存）
    path_gen = PathGenerator(config, prob_df, rng)
    num_paths = config.get('num_paths')
    cache_path = config.get('paths_cache')
    logger.info(f"开始生成 {num_paths} 条路径...")
    all_paths = path_gen.generate(num_paths, seed, cache_path)
    logger.info(f"路径生成完成，共 {len(all_paths)} 条")

    # 6. 对话生成（支持断点续传）
    checkpoint_interval = config.get('checkpoint_interval', 5000)
    checkpoint_file = os.path.join(config.get('output_dir', 'output'), "checkpoint.json")
    
    # 加载已有进度
    existing_dialogues, start_index = load_checkpoint(checkpoint_file)
    if start_index > 0:
        logger.info(f"从检查点恢复，已生成 {len(existing_dialogues)} 条对话，从第 {start_index} 条路径开始")
    else:
        existing_dialogues = []
        start_index = 0

    # 创建对话构建器（注入随机服务和日志器）
    builder = DialogueBuilder(config, df_dict, condition_evaluator, rng, logger)

    all_dialogues = existing_dialogues.copy()
    total_paths = len(all_paths)

    logger.info(f"开始生成对话，共 {total_paths} 条路径，从索引 {start_index} 开始...")
    for i in range(start_index, total_paths):
        path = all_paths[i]
        case = cases[i % len(cases)]
        prompt = prompts[i % len(prompts)]
        try:
            messages = builder.build(path, case, prompt)
            all_dialogues.append({"messages": messages})
        except Exception as e:
            logger.error(f"生成第{i}条对话时出错，路径长度: {len(path)}", exc_info=True)
            continue

        # 定期保存检查点
        if (i + 1) % checkpoint_interval == 0:
            save_checkpoint(all_dialogues, i + 1, checkpoint_file)
            logger.info(f"已生成 {i+1}/{total_paths} 条对话，检查点已保存")

    # 最终保存
    output_dir = config.get('output_dir', 'output')
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(output_dir, f"general_dialogues_{timestamp}.json")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(all_dialogues, f, ensure_ascii=False, indent=2)

    # 删除检查点文件（表示已完成）
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)

    logger.info(f"生成完成，共 {len(all_dialogues)} 条对话，保存至 {out_file}")

if __name__ == "__main__":
    main()