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

import json
import os
import logging
import argparse
from datetime import datetime
from tqdm import tqdm
import multiprocessing as mp

import pandas as pd
from core.config import load_config, auto_sync_config_from_excel
from core.data_loader import load_cases, load_prob_matrix, load_sheets
from core.factory import (
    create_case_loader,
    create_condition_evaluator,
    create_time_generator,
)
from core.logger import get_logger, init_logger
from core.path_generator import PathGenerator
from core.random_service import RandomService

# ==================== JSON 序列化（支持 orjson 加速） ====================
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


def count_jsonl_lines(filepath: str) -> int:
    """统计 JSONL 文件的行数（用于判断分片是否完整）"""
    if not os.path.exists(filepath):
        return 0
    count = 0
    with open(filepath, "r", encoding="utf-8") as f:
        for _ in f:
            count += 1
    return count


# ==================== 多进程 Worker 函数 ====================
def worker_generate(
    start_idx,
    end_idx,
    output_file,
    trace_file,
    config_dict,
    all_paths,
    cases,
    prompts,
    df_dict,
    pressure_df,
    seed,
    process_id,
    trace_enabled,
    checkpoint_interval,
    already_done=0,
):
    """
    子进程任务：生成对话并写入分片文件（JSON Lines），同时收集 trace（若启用）
    支持断点续传：already_done 表示已完成的数量，从 start_idx + already_done 开始继续
    """
    import sys
    import os
    from tqdm import tqdm

    # 确保能找到 core 模块
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

    from core.config import Config
    from core.dialogue_builder import DialogueBuilder
    from core.pressure_manager import PressureManager
    from core.factory import create_condition_evaluator
    from core.random_service import RandomService

    config = Config(config_dict)
    rng = RandomService(seed + process_id)  # 独立种子
    condition_evaluator = create_condition_evaluator(config)
    pressure_manager = PressureManager(pressure_df, rng, config)
    builder = DialogueBuilder(
        config, df_dict, condition_evaluator, rng, pressure_manager, None
    )

    total_paths = len(all_paths)
    total_cases = len(cases)

    resume_start = start_idx + already_done
    total_expected = end_idx - start_idx

    # 已完成全部，直接返回
    if already_done >= total_expected:
        print(f"进程 {process_id} 分片已完成（{already_done}/{total_expected}），跳过")
        return total_expected

    # 追加模式：从断点处继续写入
    mode = "a" if already_done > 0 else "w"
    all_traces = [] if trace_enabled else None

    # 续传时尝试加载已有 trace
    if trace_enabled and already_done > 0 and os.path.exists(trace_file):
        try:
            with open(trace_file, "r", encoding="utf-8") as f_trace:
                all_traces = json.load(f_trace)
        except (json.JSONDecodeError, IOError):
            all_traces = []

    with open(output_file, mode, encoding="utf-8") as f_out:
        for i in tqdm(
            range(resume_start, end_idx),
            desc=f"进程 {process_id}",
            position=process_id,
            leave=True,
            initial=already_done,
            total=total_expected,
        ):
            path = all_paths[i % total_paths]
            case = cases[i % total_cases]
            prompt = prompts[i % total_cases]
            try:
                messages = builder.build(path, case, prompt)
                line = dumps_json({"messages": messages})
                f_out.write(line + "\n")
                if (i - start_idx + 1) % checkpoint_interval == 0:
                    f_out.flush()
                if trace_enabled:
                    all_traces.append(builder.get_trace_data())
            except Exception as e:
                print(f"进程 {process_id} 第{i}条对话出错: {e}", file=sys.stderr)
                continue

    if trace_enabled and all_traces is not None:
        with open(trace_file, "w", encoding="utf-8") as f_trace:
            json.dump(all_traces, f_trace, ensure_ascii=False, indent=2)

    return end_idx - start_idx


# ==================== 合并分片文件（转换为标准 JSON 数组） ====================
def merge_shards_to_json(shard_files, output_file):
    """将多个 JSON Lines 分片合并为一个标准的 JSON 数组文件（保留分片以支持断点续传）"""
    with open(output_file, "w", encoding="utf-8") as f_out:
        f_out.write("[\n")
        first = True
        for shard in shard_files:
            with open(shard, "r", encoding="utf-8") as f_in:
                for line in f_in:
                    if not first:
                        f_out.write(",\n")
                    f_out.write(line.strip())
                    first = False
        f_out.write("\n]\n")


def merge_trace_shards(shard_files, output_file):
    """合并 trace 分片（每个分片是一个 JSON 列表，保留分片以支持断点续传）"""
    all_traces = []
    for shard in shard_files:
        if os.path.exists(shard) and os.path.getsize(shard) > 0:
            with open(shard, "r", encoding="utf-8") as f:
                traces = json.load(f)
                all_traces.extend(traces)
    with open(output_file, "w", encoding="utf-8") as f_out:
        json.dump(all_traces, f_out, ensure_ascii=False, indent=2)


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
    
    # 1.5 自动从 Excel 话术模板同步 modules 和 max_repeat
    config = auto_sync_config_from_excel(config)
    
    config_dict = config.to_dict()

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

    # 4. 随机服务（仅用于路径生成）
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

    # 6. 加载施压话术表（所有进程共用）
    pressure_sheet_name = config.get("pressure_sheet_name", "链接施压话术")
    try:
        pressure_df = pd.read_excel(excel_path, sheet_name=pressure_sheet_name)
        logger.info(f"加载施压话术表: {pressure_sheet_name}")
    except ValueError:
        pressure_df = pd.DataFrame()
        logger.warning(f"施压话术表 '{pressure_sheet_name}' 不存在，将跳过施压话术")

    # 7. 条件解析器与时间生成器（用于案例加载）
    condition_evaluator = create_condition_evaluator(config)
    time_gen = create_time_generator(config)
    case_loader = create_case_loader(config)
    cases, prompts = case_loader.load(rng=rng, time_gen=time_gen)
    logger.info(f"最终加载案例数量: {len(cases)}")

    # 8. 路径生成（使用 num_paths_to_generate）
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

    # 9. 对话生成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trace_enabled = config.get("trace_enabled", False)

    # ========== 统一生成模式（支持断点续传） ==========
    chunk_size = (num_dialogues + num_processes - 1) // num_processes
    ranges = []
    for p in range(num_processes):
        start = p * chunk_size
        end = min(start + chunk_size, num_dialogues)
        if start < end:
            ranges.append((start, end))

    # 准备分片文件，检查完整性以支持断点续传
    shard_files = []
    trace_shard_files = []
    tasks = []
    skipped_count = 0
    resumed_count = 0
    force_regenerate = args.force

    if force_regenerate:
        logger.warning("强制重新生成模式：将删除所有已有分片文件")

    for p, (start, end) in enumerate(ranges):
        shard_file = os.path.join(task_dir, f"shard_{p:03d}_{start}_{end}.jsonl")
        expected_lines = end - start
        shard_files.append(shard_file)

        # 强制模式：删除已有分片
        if force_regenerate and os.path.exists(shard_file):
            os.remove(shard_file)
            logger.info(f"已删除旧分片 {p}: {shard_file}")

        # 检查分片是否已完成
        already_done = count_jsonl_lines(shard_file)
        if already_done >= expected_lines:
            skipped_count += 1
            logger.info(f"分片 {p} ({start}-{end}) 已完成（{already_done}/{expected_lines}），跳过")
            if trace_enabled:
                trace_shard = os.path.join(
                    task_dir, f"trace_shard_{p:03d}_{start}_{end}.json"
                )
                trace_shard_files.append(trace_shard)
            continue

        if already_done > 0:
            resumed_count += 1
            logger.info(f"分片 {p} ({start}-{end}) 已完成 {already_done}/{expected_lines}，将续传")

        if trace_enabled:
            trace_shard = os.path.join(
                task_dir, f"trace_shard_{p:03d}_{start}_{end}.json"
            )
            trace_shard_files.append(trace_shard)
        else:
            trace_shard = None

        tasks.append(
            (
                start,
                end,
                shard_file,
                trace_shard,
                config_dict,
                all_paths,
                cases,
                prompts,
                df_dict,
                pressure_df,
                seed,
                p + 1,  # process_id
                trace_enabled,
                checkpoint_interval,
                already_done,
            )
        )

    if skipped_count > 0:
        logger.info(f"断点续传：跳过 {skipped_count} 个已完成分片")
    if resumed_count > 0:
        logger.info(f"断点续传：{resumed_count} 个分片将从断点继续")

    if tasks:
        if num_processes > 1:
            logger.info(f"启动 {len(tasks)} 个进程并行生成对话...")
            with mp.Pool(processes=num_processes) as pool:
                pool.starmap(worker_generate, tasks)
        else:
            logger.info(f"单进程模式，生成 {len(tasks)} 个分片...")
            for task in tasks:
                worker_generate(*task)
    else:
        logger.info("所有分片已完成，无需重新生成")

    # 合并对话分片为标准 JSON 数组
    final_output_file = os.path.join(
        task_dir, f"{task_name}_generate_{num_dialogues}_{seed}_{timestamp}.json"
    )
    logger.info("合并对话分片...")
    merge_shards_to_json(shard_files, final_output_file)

    # 合并 trace 分片
    trace_file = None
    if trace_enabled and trace_shard_files:
        trace_file = os.path.join(traces_dir, f"{task_name}_traces_{num_dialogues}_{seed}_{timestamp}.json")
        logger.info("合并 trace 分片...")
        merge_trace_shards(trace_shard_files, trace_file)
        logger.info(f"追踪数据已保存至 {trace_file}")

    logger.info(f"生成完成，共 {num_dialogues} 条对话，保存至 {final_output_file}")

    # 10. 自动分析（如果配置启用且 trace 存在）
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
