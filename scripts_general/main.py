#!/usr/bin/env python3
"""
多轮对话生成脚本（重构版）
基于配置驱动、模块化设计，支持通用催收模板。
支持断点续传和可选的详细追踪（trace）。
"""

import json
import os
from datetime import datetime

import pandas as pd
from core.config import load_config
from core.data_loader import load_cases, load_prob_matrix, load_sheets
from core.dialogue_builder import DialogueBuilder
from core.factory import create_condition_evaluator
from core.logger import get_logger, init_logger
from core.path_generator import PathGenerator
from core.pressure_manager import PressureManager
from core.random_service import RandomService


def save_checkpoint(dialogues: list, next_index: int, checkpoint_file: str):
    """保存对话生成进度"""
    with open(checkpoint_file, "w", encoding="utf-8") as f:
        json.dump(
            {"next_index": next_index, "dialogues": dialogues},
            f,
            ensure_ascii=False,
            indent=2,
        )


def load_checkpoint(checkpoint_file: str):
    """加载检查点，返回 (dialogues, next_index)"""
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("dialogues", []), data.get("next_index", 0)
    return [], 0


def main():
    # 1. 加载配置
    config_path = "configs/general.yaml"
    config = load_config(config_path)
    logger = None  # 稍后初始化

    # 2. 读取基本参数
    task_name = config.get("task_name", "general")
    num_paths = config.get("num_paths")
    seed = config.get("random_seed", 42)
    output_root = config.get("output_dir", "output")
    paths_cache_dir = config.get("paths_cache_dir", "paths")
    checkpoint_interval = config.get("checkpoint_interval", 5000)

    # 构建任务子目录名：{task_name}_{num_paths}_{seed}
    task_dir_name = f"{task_name}_{num_paths}_{seed}"
    task_dir = os.path.join(output_root, task_dir_name)
    intermediate_dir = os.path.join(task_dir, "intermediate")
    logs_dir = os.path.join(intermediate_dir, "logs")
    traces_dir = os.path.join(intermediate_dir, "traces")
    analysis_dir = os.path.join(intermediate_dir, "analysis")  # 可选

    # 创建必要的目录
    os.makedirs(logs_dir, exist_ok=True)
    os.makedirs(traces_dir, exist_ok=True)
    os.makedirs(analysis_dir, exist_ok=True)

    # 3. 初始化日志（传入日志目录）
    # 注意：需要修改 logger.py 以支持 log_dir 参数
    init_logger(config, log_dir=logs_dir)
    logger = get_logger()

    logger.info("=== 对话生成系统启动 ===")
    logger.info(f"配置文件: {config_path}")
    logger.info(f"任务目录: {task_dir}")

    # 4. 随机服务
    rng = RandomService(seed)
    logger.info(f"随机种子: {seed}")

    # 5. 加载数据
    logger.info("加载 Excel 模块...")
    excel_path = config.get("excel_path")
    modules = config.get("modules")
    df_dict = load_sheets(excel_path, modules)

    logger.info("加载概率矩阵...")
    prob_path = config.get("prob_path")
    prob_df = load_prob_matrix(prob_path, modules)

    logger.info("加载案例...")
    cases_dir = config.get("cases_dir")
    cases, prompts = load_cases(cases_dir, rng=rng)
    logger.info(f"加载案例数量: {len(cases)}")

    # 6. 加载施压话术表
    pressure_df = pd.read_excel(excel_path, sheet_name="链接施压话术")
    pressure_manager = PressureManager(pressure_df, rng, config)

    # 7. 条件解析器
    condition_evaluator = create_condition_evaluator(config)

    # 8. 路径生成（使用独立于任务的缓存目录）
    # 路径缓存放在 output_root/paths/ 下，文件名由模板决定
    paths_cache_template = config.get(
        "paths_cache", "output/paths/all_paths_{num_paths}_{seed}.json"
    )
    # 确保路径缓存目录存在
    paths_cache_dir_abs = os.path.join(output_root, paths_cache_dir)
    os.makedirs(paths_cache_dir_abs, exist_ok=True)
    # 生成最终缓存路径
    cache_path = paths_cache_template.format(num_paths=num_paths, seed=seed)
    # 如果配置中的路径已包含 output_root，则直接使用，否则基于 output_root 拼接
    if not os.path.isabs(cache_path) and not cache_path.startswith(output_root):
        cache_path = os.path.join(output_root, cache_path)

    path_gen = PathGenerator(config, prob_df, rng, logger)
    logger.info(f"开始生成 {num_paths} 条路径...")
    all_paths = path_gen.generate(num_paths, seed, cache_path=cache_path)
    logger.info(f"路径生成完成，共 {len(all_paths)} 条")

    # 9. 对话生成（支持断点续传）
    checkpoint_file = os.path.join(task_dir, "checkpoint.json")
    existing_dialogues, start_index = load_checkpoint(checkpoint_file)
    if start_index > 0:
        logger.info(
            f"从检查点恢复，已生成 {len(existing_dialogues)} 条对话，从第 {start_index} 条路径开始"
        )
    else:
        existing_dialogues = []
        start_index = 0

    # 创建对话构建器
    builder = DialogueBuilder(
        config, df_dict, condition_evaluator, rng, pressure_manager, logger
    )

    all_dialogues = existing_dialogues.copy()
    all_traces = []
    total_paths = len(all_paths)

    logger.info(f"开始生成对话，共 {total_paths} 条路径，从索引 {start_index} 开始...")
    for i in range(start_index, total_paths):
        path = all_paths[i]
        case = cases[i % len(cases)]
        prompt = prompts[i % len(prompts)]
        try:
            messages = builder.build(path, case, prompt)
            all_dialogues.append({"messages": messages})
            if config.get("trace_enabled", False):
                trace_data = builder.get_trace_data()
                all_traces.append(trace_data)
        except Exception as e:
            logger.error(f"生成第{i}条对话时出错，路径长度: {len(path)}", exc_info=True)
            continue

        if (i + 1) % checkpoint_interval == 0:
            save_checkpoint(all_dialogues, i + 1, checkpoint_file)
            logger.info(f"已生成 {i+1}/{total_paths} 条对话，检查点已保存")

    # 最终保存对话
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(task_dir, f"general_dialogues_{timestamp}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_dialogues, f, ensure_ascii=False, indent=2)

    # 删除检查点文件（表示已完成）
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)

    logger.info(f"生成完成，共 {len(all_dialogues)} 条对话，保存至 {out_file}")

    # 保存追踪数据（如果启用）
    if config.get("trace_enabled", False) and all_traces:
        trace_file = os.path.join(traces_dir, f"traces_{timestamp}.json")
        with open(trace_file, "w", encoding="utf-8") as f:
            json.dump(all_traces, f, ensure_ascii=False, indent=2)
        logger.info(f"追踪数据已保存至 {trace_file}")


if __name__ == "__main__":
    main()
