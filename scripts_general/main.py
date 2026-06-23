#!/usr/bin/env python3
"""
多轮对话生成脚本（重构版）
基于配置驱动、模块化设计，支持通用催收模板。
支持断点续传和可选的详细追踪（trace）。
"""

import json
import os
import sys
import logging
from datetime import datetime
from tqdm import tqdm

import pandas as pd
from core.config import load_config
from core.data_loader import load_cases, load_prob_matrix, load_sheets
from core.dialogue_builder import DialogueBuilder
from core.factory import (
    create_case_loader,
    create_condition_evaluator,
    create_time_generator,
)
from core.logger import get_logger, init_logger
from core.path_generator import PathGenerator
from core.pressure_manager import PressureManager
from core.random_service import RandomService

# ==================== JSON 序列化优化 ====================
try:
    import orjson

    USE_ORJSON = True
except ImportError:
    USE_ORJSON = False
    import json


def dumps_json(obj):
    """序列化 JSON 对象，支持 orjson 加速"""
    if USE_ORJSON:
        return orjson.dumps(obj, option=orjson.OPT_SERIALIZE_NUMPY).decode("utf-8")
    else:
        return json.dumps(obj, ensure_ascii=False)


# ==================== 检查点函数（保存文件路径） ====================
def save_checkpoint(
    next_index: int, checkpoint_file: str, dialogues_file: str, traces_file: str = None
):
    """保存对话生成进度，包含文件路径"""
    data = {
        "next_index": next_index,
        "dialogues_file": dialogues_file,
    }
    if traces_file:
        data["traces_file"] = traces_file
    with open(checkpoint_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_checkpoint(checkpoint_file: str):
    """加载检查点，返回 (next_index, dialogues_file, traces_file)"""
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (
            data.get("next_index", 0),
            data.get("dialogues_file"),
            data.get("traces_file"),
        )
    return 0, None, None


# ==================== 主函数 ====================
def main():
    # 1. 加载配置
    config_path = "configs/general_Xiaoying_dynamic_0615.yaml"
    config = load_config(config_path)

    # 2. 读取基本参数（修改部分：支持 num_dialogues 和 num_paths_to_generate）
    task_name = config.get("task_name", "general")
    # 生成对话总数
    num_dialogues = config.get("num_dialogues", config.get("num_paths", 40000))
    # 实际生成的不重复路径数（如果未配置则等于对话数，保持向后兼容）
    num_paths_to_generate = config.get("num_paths_to_generate", num_dialogues)
    seed = config.get("random_seed", 42)
    output_root = config.get("output_dir", "output")
    paths_cache_dir = config.get("paths_cache_dir", "paths")
    checkpoint_interval = config.get("checkpoint_interval", 5000)

    # 构建任务子目录名：使用对话总数（因为输出文件数量是对话数）
    task_dir_name = f"{task_name}_{num_dialogues}_{seed}"
    task_dir = os.path.join(output_root, task_dir_name)
    intermediate_dir = os.path.join(task_dir, "intermediate")
    logs_dir = os.path.join(intermediate_dir, "logs")
    traces_dir = os.path.join(intermediate_dir, "traces")
    analysis_dir = os.path.join(intermediate_dir, "analysis")

    # 创建必要的目录
    os.makedirs(logs_dir, exist_ok=True)
    os.makedirs(traces_dir, exist_ok=True)
    os.makedirs(analysis_dir, exist_ok=True)

    # 3. 初始化日志（调整终端级别为 INFO）
    init_logger(config, log_dir=logs_dir)
    logger = get_logger()

    # 新增：调整终端 handler 级别为 WARNING
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setLevel(logging.INFO)

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
    case_loader = create_case_loader(config)
    cases, prompts = case_loader.load(rng=rng)
    logger.info(f"加载案例数量: {len(cases)}")

    # 6. 加载施压话术表
    pressure_df = pd.read_excel(excel_path, sheet_name="链接施压话术")
    pressure_manager = PressureManager(pressure_df, rng, config)

    # 7. 条件解析器与时间生成器
    condition_evaluator = create_condition_evaluator(config)
    time_gen = create_time_generator(config)
    # 重新加载案例（传入 time_gen）
    case_loader = create_case_loader(config)
    cases, prompts = case_loader.load(rng=rng, time_gen=time_gen)
    logger.info(f"最终加载案例数量: {len(cases)}")

    # 8. 路径生成
    paths_cache_template = config.get(
        "paths_cache", "output/paths/all_paths_{num_paths}_{seed}.json"
    )
    paths_cache_dir_abs = os.path.join(output_root, paths_cache_dir)
    os.makedirs(paths_cache_dir_abs, exist_ok=True)
    # 使用 num_paths_to_generate 生成缓存文件名
    cache_path = paths_cache_template.format(num_paths=num_paths_to_generate, seed=seed)
    if not os.path.isabs(cache_path) and not cache_path.startswith(output_root):
        cache_path = os.path.join(output_root, cache_path)

    path_gen = PathGenerator(config, prob_df, rng, logger)
    logger.info(f"开始生成 {num_paths_to_generate} 条路径...")
    all_paths = path_gen.generate(num_paths_to_generate, seed, cache_path=cache_path)
    logger.info(f"路径生成完成，共 {len(all_paths)} 条")

    # 9. 对话生成（流式写入 + 断点续传）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(task_dir, f"general_dialogues_{timestamp}.json")
    checkpoint_file = os.path.join(task_dir, "checkpoint.json")

    # 恢复检查点
    start_index, saved_dialogues_file, saved_traces_file = load_checkpoint(
        checkpoint_file
    )
    if start_index > 0 and saved_dialogues_file:
        out_file = saved_dialogues_file  # 继续使用同一个文件
        logger.info(f"从检查点恢复，继续写入文件: {out_file}")
    else:
        # 新任务，清空文件（如果存在则覆盖）
        with open(out_file, "w", encoding="utf-8") as f:
            pass
        start_index = 0

    # 以追加模式打开对话文件
    f_dialogues = open(out_file, "a", encoding="utf-8")

    # 创建对话构建器
    builder = DialogueBuilder(
        config, df_dict, condition_evaluator, rng, pressure_manager, logger
    )

    all_traces = []  # 如果 trace 启用，收集到内存（可考虑分批写入）
    total_paths = len(all_paths)

    logger.info(
        f"开始生成对话，共 {num_dialogues} 条对话（复用 {total_paths} 条路径），从索引 {start_index} 开始..."
    )

    try:
        for i in tqdm(range(start_index, num_dialogues), desc="生成对话", unit="条"):
            path = all_paths[i % total_paths]
            case = cases[i % len(cases)]
            prompt = prompts[i % len(prompts)]
            try:
                messages = builder.build(path, case, prompt)
                # 写入 JSON Lines
                line = dumps_json({"messages": messages})
                f_dialogues.write(line + "\n")
                if (i + 1) % 1000 == 0:
                    f_dialogues.flush()

                if config.get("trace_enabled", False):
                    trace_data = builder.get_trace_data()
                    all_traces.append(trace_data)
            except Exception as e:
                logger.error(
                    f"生成第{i}条对话时出错，路径长度: {len(path)}", exc_info=True
                )
                continue

            if (i + 1) % checkpoint_interval == 0:
                # 保存检查点（包含文件路径）
                traces_file = None
                if config.get("trace_enabled", False) and all_traces:
                    # 如果有 trace，暂不写入文件，仅记录路径供恢复时参考
                    traces_file = os.path.join(traces_dir, f"traces_{timestamp}.json")
                save_checkpoint(i + 1, checkpoint_file, out_file, traces_file)
                logger.info(f"已生成 {i+1}/{num_dialogues} 条对话，检查点已保存")

    except KeyboardInterrupt:
        logger.warning("用户中断生成，保存检查点...")
        save_checkpoint(i + 1, checkpoint_file, out_file, None)
        f_dialogues.close()
        sys.exit(0)
    except Exception as e:
        logger.error(f"生成过程中发生错误: {e}", exc_info=True)
        save_checkpoint(i + 1, checkpoint_file, out_file, None)
        f_dialogues.close()
        raise

    f_dialogues.close()

    # 完成生成，删除检查点
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)

    logger.info(f"生成完成，共 {num_dialogues} 条对话，保存至 {out_file}")

    # 保存追踪数据（如果启用）
    if config.get("trace_enabled", False) and all_traces:
        trace_file = os.path.join(traces_dir, f"traces_{timestamp}.json")
        with open(trace_file, "w", encoding="utf-8") as f:
            json.dump(all_traces, f, ensure_ascii=False, indent=2)
        logger.info(f"追踪数据已保存至 {trace_file}")

    # ========== 自动分析（如果配置启用） ==========
    if config.get("auto_analysis.enabled", False):
        trace_file = os.path.join(traces_dir, f"traces_{timestamp}.json")
        if os.path.exists(trace_file):
            analysis_output = os.path.join(
                task_dir, "intermediate", "analysis", timestamp
            )
            plot_format = config.get("auto_analysis.format", "html")
            try:
                from core.analyzer import DefaultAnalyzer

                # 读取压力配置（用于图表标注）
                pressure_config = {
                    "start_prob": config.get("pressure_start_prob"),
                    "end_prob": config.get("pressure_end_prob"),
                    "exponent": config.get("pressure_curve_exponent"),
                    "max_total": config.get("pressure_max_total"),
                    "mode": config.get("pressure_strategy", {}).get(
                        "type", "normalized"
                    ),
                }
                # 如果是 sigmoid 策略，添加 slope
                strategy_cfg = config.get("pressure_strategy", {})
                if strategy_cfg.get("type") == "sigmoid":
                    pressure_config["slope"] = strategy_cfg.get("slope", 10.0)
                # 如果是 absolute 策略，添加 max_expected_modules
                if strategy_cfg.get("type") == "absolute":
                    pressure_config["max_expected"] = config.get(
                        "max_expected_modules", 15
                    )
                # 过滤 None
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
        else:
            logger.warning(f"未找到 trace 文件 {trace_file}，跳过自动分析")


if __name__ == "__main__":
    main()
