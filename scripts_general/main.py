#!/usr/bin/env python3
"""
多轮对话生成脚本（重构版）
基于配置驱动、模块化设计，支持通用催收模板。
统一单进程/多进程代码路径，支持断点续传、流式写入、追踪和自动分析。

# 使用默认配置文件
python scripts_general/main.py

# 指定自定义配置文件（短选项）
python scripts_general/main.py -c configs/xiaoying_v2/general_Xiaoying_0702_3w_debug.yaml

# 指定自定义配置文件（长选项）
python scripts_general/main.py --config configs/xiaoying_v2/general_Xiaoying_0702_3w_debug.yaml

# 强制重新生成（忽略断点）
python scripts_general/main.py -f

# 查看帮助信息
python scripts_general/main.py -h
"""

import os
import logging
import argparse
from datetime import datetime

import pandas as pd
from core.config import load_config, sync_config_from_prob
from core.data_loader import load_prob_matrix, load_sheets
from core.factory import (
    create_case_loader,
    create_time_generator,
)
from core.logger import get_logger, init_logger
from core.path_generator import PathGenerator
from core.parallel_generator import generate_dialogues
from core.random_service import RandomService


# ==================== 主函数 ====================
def main():
    parser = argparse.ArgumentParser(description="多轮对话生成脚本")
    parser.add_argument(
        "-c", "--config",
        type=str,
        default="configs/xiaoying_v2/general_Xiaoying_0703_4w.yaml",
        help="配置文件路径（默认: configs/xiaoying_v2/general_Xiaoying_0703_4w.yaml）"
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="强制重新生成，忽略已完成的分片（删除旧分片文件）"
    )
    args = parser.parse_args()

    # 1. 加载配置
    config_path = args.config
    config = load_config(config_path)

    # 2. 读取基本参数（兼容旧版 num_paths）
    task_name = config.get("task_name", "general")
    num_dialogues = config.get("num_dialogues", config.get("num_paths", 40000))
    num_paths_to_generate = config.get("num_paths_to_generate", num_dialogues)
    seed = config.get("random_seed", 42)
    output_root = config.get("output_dir", "output")
    paths_cache_dir = config.get("paths_cache_dir", "paths")
    checkpoint_interval = config.get("checkpoint_interval", 5000)

    # 多进程配置
    mp_cfg = config.get("multiprocessing", {})
    num_processes = mp_cfg.get("num_processes", 1)
    if num_processes > 1:
        print(f"多进程模式启用，进程数: {num_processes}")
    else:
        print("单进程模式，进程数: 1")

    # 任务目录
    task_dir_name = f"{task_name}_{num_dialogues}_{seed}"
    task_dir = os.path.join(output_root, task_dir_name)
    intermediate_dir = os.path.join(task_dir, "intermediate")
    logs_dir = os.path.join(intermediate_dir, "logs")
    traces_dir = os.path.join(intermediate_dir, "traces")
    analysis_dir = os.path.join(intermediate_dir, "analysis")

    os.makedirs(logs_dir, exist_ok=True)
    os.makedirs(traces_dir, exist_ok=True)
    os.makedirs(analysis_dir, exist_ok=True)

    # 3. 初始化日志（主进程）
    init_logger(config, log_dir=logs_dir)
    logger = get_logger()
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setLevel(logging.INFO)

    logger.info("=== 对话生成系统启动 ===")
    logger.info(f"配置文件: {config_path}")
    logger.info(f"任务目录: {task_dir}")

    # 4. 加载 prob 表 → 提取 modules（唯一来源）
    prob_path = config.get("prob_path")
    logger.info(f"加载概率矩阵: {prob_path}")
    prob_df, modules = load_prob_matrix(prob_path)
    logger.info(f"概率矩阵加载完成，共 {len(modules)} 个模块: {modules}")

    # 5. 以 modules 为准，从 Excel 同步 max_repeat
    config = sync_config_from_prob(config, modules)
    config_dict = config.to_dict()

    # 6. 随机服务（仅用于路径生成）
    rng = RandomService(seed)
    logger.info(f"随机种子: {seed}")

    # 7. 加载 Excel 模块数据（按 prob 表 modules 校验）
    logger.info("加载 Excel 模块...")
    excel_path = config.get("excel_path")
    df_dict = load_sheets(excel_path, modules)

    # 8. 加载施压话术表（所有进程共用）
    pressure_sheet_name = config.get("pressure_sheet_name", "链接施压话术")
    try:
        pressure_df = pd.read_excel(excel_path, sheet_name=pressure_sheet_name)
        logger.info(f"加载施压话术表: {pressure_sheet_name}")
    except ValueError:
        pressure_df = pd.DataFrame()
        logger.warning(f"施压话术表 '{pressure_sheet_name}' 不存在，将跳过施压话术")

    # 9. 时间生成器与案例加载
    time_gen = create_time_generator(config)
    case_loader = create_case_loader(config)
    cases, prompts = case_loader.load(rng=rng, time_gen=time_gen)
    logger.info(f"加载案例数量: {len(cases)}")

    # 10. 路径生成（使用 num_paths_to_generate）
    paths_cache_template = config.get(
        "paths_cache", "output/paths/all_paths_{num_paths}_{seed}.json"
    )
    paths_cache_dir_abs = os.path.join(output_root, paths_cache_dir)
    os.makedirs(paths_cache_dir_abs, exist_ok=True)
    cache_path = paths_cache_template.format(num_paths=num_paths_to_generate, seed=seed)
    if not os.path.isabs(cache_path) and not cache_path.startswith(output_root):
        cache_path = os.path.join(output_root, cache_path)

    path_gen = PathGenerator(config, prob_df, rng, logger)
    logger.info(f"开始生成 {num_paths_to_generate} 条路径...")
    all_paths = path_gen.generate(num_paths_to_generate, seed, cache_path=cache_path)
    logger.info(f"路径生成完成，共 {len(all_paths)} 条")

    # 9. 对话生成（委托给 parallel_generator，统一单/多进程 + 断点续传）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trace_enabled = config.get("trace_enabled", False)

    final_output_file, trace_file = generate_dialogues(
        num_dialogues=num_dialogues,
        num_processes=num_processes,
        task_dir=task_dir,
        traces_dir=traces_dir,
        task_name=task_name,
        seed=seed,
        timestamp=timestamp,
        config_dict=config_dict,
        all_paths=all_paths,
        cases=cases,
        prompts=prompts,
        df_dict=df_dict,
        pressure_df=pressure_df,
        trace_enabled=trace_enabled,
        checkpoint_interval=checkpoint_interval,
        logger=logger,
        force_regenerate=args.force,
    )

    # 11. 自动分析（如果配置启用且 trace 存在）
    if (
        config.get("analysis.enabled", False)
        and trace_file
        and os.path.exists(trace_file)
    ):
        analysis_output = os.path.join(task_dir, "intermediate", "analysis", f"{task_name}_generate_analysis_{timestamp}")
        plot_format = config.get("analysis.format", "html")
        try:
            from core.analyzer import DefaultAnalyzer

            pressure_config = {
                "start_prob": config.get("pressure_start_prob"),
                "end_prob": config.get("pressure_end_prob"),
                "exponent": config.get("pressure_curve_exponent"),
                "max_total": config.get("pressure_max_total"),
                "mode": config.get("pressure_strategy", {}).get("type", "normalized"),
            }
            strategy_cfg = config.get("pressure_strategy", {})
            if strategy_cfg.get("type") == "sigmoid":
                pressure_config["slope"] = strategy_cfg.get("slope", 10.0)
            if strategy_cfg.get("type") == "absolute":
                pressure_config["max_expected"] = config.get("max_expected_modules", 15)
            pressure_config = {
                k: v for k, v in pressure_config.items() if v is not None
            }
            analyzer = DefaultAnalyzer(
                format=plot_format, pressure_config=pressure_config
            )
            analyzer.analyze(trace_file, analysis_output)
            logger.info(f"自动分析完成，报告保存在 {analysis_output}")
        except Exception as e:
            logger.error(f"自动分析失败: {e}", exc_info=True)
    elif config.get("analysis.enabled", False):
        logger.warning("trace 文件不存在，跳过自动分析")


if __name__ == "__main__":
    main()
