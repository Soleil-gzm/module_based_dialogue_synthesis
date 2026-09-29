#!/usr/bin/env python3
"""
多轮对话生成脚本（单任务 + 多任务批量）。

用法：
    # 单任务（旧方式，兼容）
    python scripts_general/main.py -c configs/M0/M0_WN_AN.yaml

    # 多任务批量（新方式）
    python scripts_general/main.py -c configs/M0/tasks_M0.yaml

    # 多任务中只跑指定任务
    python scripts_general/main.py -c configs/M0/tasks_M0.yaml -t M0_WN_AN

    # 强制重新生成
    python scripts_general/main.py -c configs/M0/tasks_M0.yaml -f

日志说明：
    - 每个任务的详细日志：output/{task_dir}/intermediate/logs/
    - 批量汇总日志：output/batch_logs/batch_{timestamp}.log
"""

import argparse
import logging
import os
import sys
from datetime import datetime

import pandas as pd
from core.data.data_loader import (
    load_pressure_sheet,
    load_prob_matrix,
    load_sheets,
)
from core.generation.config import (
    Config,
    deep_merge,
    load_config,
    load_tasks_config,
    sync_config_from_prob,
)
from core.generation.factory import create_case_loader, create_time_generator
from core.generation.parallel_generator import generate_dialogues
from core.utils.logger import get_logger, init_logger
from core.utils.path_generator import PathGenerator
from core.utils.random_service import RandomService

# ============================================================
# 日志工具
# ============================================================
def _reset_dialogue_logger():
    """
    重置 DialogueBuilder logger，使得下一个任务能重新初始化日志文件。
    需要同时清空 logger.py 中的单例和 logging 模块中的 handlers。
    """
    # 1. 清空 logger.py 单例
    try:
        import core.utils.logger as logger_module

        logger_module._logger_instance = None
    except Exception:
        pass

    # 2. 清空 DialogueBuilder logger 的所有 handler
    lg = logging.getLogger("DialogueBuilder")
    for h in list(lg.handlers):
        lg.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
    lg.setLevel(logging.NOTSET)


def setup_batch_logger(output_root: str) -> logging.Logger:
    """
    创建批量汇总日志 logger，写入 output/batch_logs/batch_{timestamp}.log。
    同时输出到控制台。
    """
    batch_log_dir = os.path.join(output_root, "batch_logs")
    os.makedirs(batch_log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(batch_log_dir, f"batch_{timestamp}.log")

    batch_logger = logging.getLogger("BatchSummary")
    batch_logger.setLevel(logging.INFO)
    batch_logger.propagate = False
    # 避免重复 handler
    for h in list(batch_logger.handlers):
        batch_logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    fmt = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    batch_logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.INFO)
    batch_logger.addHandler(ch)

    batch_logger.info(f"批量日志文件: {log_file}")
    return batch_logger


# ============================================================
# 单任务执行
# ============================================================
def run_single_task(
    config: Config,
    force_regenerate: bool = False,
    batch_logger: logging.Logger = None,
) -> bool:
    """
    执行单个任务的完整流程。
    返回 True 表示成功，False 表示失败（不抛异常）。
    """
    task_name = config.get("task_name", "general")

    def _log_info(msg):
        if batch_logger:
            batch_logger.info(f"[{task_name}] {msg}")

    def _log_error(msg, exc_info=False):
        if batch_logger:
            batch_logger.error(f"[{task_name}] {msg}", exc_info=exc_info)

    # ---------- 路径准备 ----------
    num_dialogues = config.get("num_dialogues", config.get("num_paths", 40000))
    num_paths_to_generate = config.get("num_paths_to_generate", num_dialogues)
    seed = config.get("random_seed", 42)
    output_root = config.get("output_dir", "output")
    paths_cache_dir = config.get("paths_cache_dir", "paths")
    checkpoint_interval = config.get("checkpoint_interval", 5000)

    mp_cfg = config.get("multiprocessing", {})
    num_processes = mp_cfg.get("num_processes", 1)

    task_dir_name = f"{task_name}_{num_dialogues}_{seed}"
    task_dir = os.path.join(output_root, task_dir_name)
    intermediate_dir = os.path.join(task_dir, "intermediate")
    logs_dir = os.path.join(intermediate_dir, "logs")
    traces_dir = os.path.join(intermediate_dir, "traces")
    analysis_dir = os.path.join(intermediate_dir, "analysis")

    os.makedirs(logs_dir, exist_ok=True)
    os.makedirs(traces_dir, exist_ok=True)
    os.makedirs(analysis_dir, exist_ok=True)

    # ---------- 重置并初始化日志 ----------
    _reset_dialogue_logger()
    init_logger(config, log_dir=logs_dir)
    logger = get_logger()
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setLevel(logging.INFO)

    logger.info("=" * 60)
    logger.info(f"=== 任务开始: {task_name} ===")
    logger.info(f"任务目录: {task_dir}")
    logger.info(
        f"进程数: {num_processes} | seed: {seed} | num_paths: {num_paths_to_generate}"
    )
    _log_info(f"开始，日志目录: {logs_dir}")

    # ---------- 加载 prob → modules ----------
    prob_path = config.get("prob_path")
    auto_cfg = config.get("prob_auto_generate") or {}
    if auto_cfg.get("enabled", False):
        from core.data.prob_generator import generate_prob_from_excel

        excel_path_for_gen = config.get("excel_path")
        logger.info("启用 prob 自动生成，开始根据话术 Excel 生成 prob 表...")
        prob_path = generate_prob_from_excel(
            excel_path=excel_path_for_gen,
            categories_yaml_path=auto_cfg.get("categories_yaml"),
            output_path=auto_cfg.get("output_path"),
            compress_mode=auto_cfg.get("compress_mode", "log"),
            save_candidates=auto_cfg.get("save_candidates", False),
        )
        logger.info(f"prob 表已自动生成，将使用: {prob_path}")
    else:
        logger.info(f"使用手动指定的 prob 表: {prob_path}")

    logger.info(f"加载概率矩阵: {prob_path}")
    prob_df, modules = load_prob_matrix(prob_path)
    logger.info(f"概率矩阵加载完成，共 {len(modules)} 个模块")

    config = sync_config_from_prob(config, modules)
    config_dict = config.to_dict()

    rng = RandomService(seed)
    logger.info(f"随机种子: {seed}")

    # ---------- 加载 Excel 模块 ----------
    logger.info("加载 Excel 模块...")
    excel_path = config.get("excel_path")
    df_dict = load_sheets(excel_path, modules)

    # ---------- 加载施压话术表 ----------
    pressure_sheet_name = config.get("pressure_sheet_name", "链接话术")
    try:
        pressure_df = load_pressure_sheet(excel_path, sheet_name=pressure_sheet_name)
        if pressure_df.empty:
            logger.warning(f"施压话术表 '{pressure_sheet_name}' 为空，将跳过施压话术")
        else:
            logger.info(f"加载施压话术表: {pressure_sheet_name}（{len(pressure_df)} 行）")
    except ValueError as e:
        pressure_df = pd.DataFrame()
        logger.warning(f"施压话术表加载失败: {e}，将跳过施压话术")

    # ---------- case 自动生成（可选） ----------
    case_auto_cfg = config.get("case_auto_generate") or {}
    if case_auto_cfg.get("enabled", False):
        from core.data.case_generator import generate_cases_if_needed

        replace_dir_for_gen = config.get("case_loader.replace_dir")
        system_dir_for_gen = config.get("case_loader.system_dir")
        if not replace_dir_for_gen or not system_dir_for_gen:
            raise ValueError(
                "启用 case_auto_generate 时必须配置 case_loader.replace_dir 和 case_loader.system_dir"
            )
        logger.info("启用 case 自动生成，开始生成 case 文件...")
        generate_cases_if_needed(
            generator_type=case_auto_cfg.get("generator_type"),
            seed=seed,
            total_cases=case_auto_cfg.get("num_cases"),
            system_dir=system_dir_for_gen,
            replace_dir=replace_dir_for_gen,
            prompt_system_path=case_auto_cfg.get("prompt_system_path"),
            prompt_replace_path=case_auto_cfg.get("prompt_replace_path"),
            combinations_path=case_auto_cfg.get("combinations_path"),
            testify=case_auto_cfg.get("testify"),
            force_regenerate=case_auto_cfg.get("force_regenerate", False),
        )

    time_gen = create_time_generator(config)
    case_loader = create_case_loader(config)
    cases, prompts = case_loader.load(rng=rng, time_gen=time_gen)
    logger.info(f"加载案例数量: {len(cases)}")

    # ---------- 路径生成 ----------
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

    # ---------- 对话生成 ----------
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
        force_regenerate=force_regenerate,
    )

    # ---------- 对话去重 ----------
    if config.get("dedup.enabled", True):
        try:
            from core.generation.dedup import DialogueDeduplicator

            deduplicator = DialogueDeduplicator(
                threshold=config.get("dedup.threshold", 0.85),
                ignore_numbers=config.get("dedup.ignore_numbers", True),
                output_suffix=config.get("dedup.output_suffix", "_dup"),
            )
            result = deduplicator.deduplicate_file(final_output_file)
            if result is None:
                logger.warning("soleil 未安装，跳过对话去重")
            else:
                dup_file, stats = result
                logger.info(
                    f"对话去重完成: 总{stats['total_dialogues']}条, "
                    f"含重复{stats['duplicate_dialogues']}条, "
                    f"删除轮对{stats['removed_pairs']}个, 输出 {dup_file}"
                )
        except Exception as e:
            logger.error(f"对话去重失败: {e}", exc_info=True)

    # ---------- 自动分析 ----------
    if (
        config.get("analysis.enabled", False)
        and trace_file
        and os.path.exists(trace_file)
    ):
        analysis_output = os.path.join(
            task_dir,
            "intermediate",
            "analysis",
            f"{task_name}_generate_analysis_{timestamp}",
        )
        plot_format = config.get("analysis.format", "html")
        try:
            from core.analysis.analyzer import DefaultAnalyzer

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

            diversity_modules = config.get("analysis.diversity_modules", [])
            if diversity_modules:
                from core.analysis.analyzer import ModuleDiversityAnalyzer

                div_analyzer = ModuleDiversityAnalyzer(modules=diversity_modules)
                div_analyzer.analyze(trace_file, analysis_output)
                logger.info(f"模块多样性分析完成，报告保存在 {analysis_output}")

            if config.get("analysis.coverage_enabled", False):
                from core.analysis.analyze_coverage import analyze_coverage

                cov_report = analyze_coverage(
                    trace_path=trace_file,
                    excel_path=excel_path,
                    prob_path=prob_path,
                    output_dir=analysis_output,
                )
                logger.info(f"数据检测报告已生成: {cov_report}")
        except Exception as e:
            logger.error(f"自动分析失败: {e}", exc_info=True)

    logger.info(f"=== 任务完成: {task_name} ===")
    logger.info("=" * 60)
    _log_info("完成")
    return True


# ============================================================
# 入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="多轮对话生成脚本（支持单/多任务）")
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        required=True,
        help="配置文件路径（单任务 YAML 或 tasks_*.yaml）",
    )
    parser.add_argument(
        "-t",
        "--task",
        type=str,
        default=None,
        help="只运行指定任务（按 name 匹配），仅多任务模式有效",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="强制重新生成，忽略已完成的分片",
    )
    args = parser.parse_args()

    # ---------- 判定单任务 / 多任务 ----------
    base_dict, tasks = load_tasks_config(args.config)

    if not tasks:
        # ========== 单任务模式（向后兼容） ==========
        print(f"单任务模式: {args.config}")
        config = load_config(args.config)
        try:
            run_single_task(config, force_regenerate=args.force, batch_logger=None)
        except Exception as e:
            logging.getLogger("DialogueBuilder").error(
                f"任务失败: {e}", exc_info=True
            )
            print(f"❌ 任务失败: {e}")
            sys.exit(1)
        return

    # ========== 多任务模式 ==========
    output_root = base_dict.get("output_dir", "output")
    batch_logger = setup_batch_logger(output_root)

    total = len(tasks)
    # 统计需要执行的任务（先做一遍 enabled 与 -t 过滤，方便日志）
    run_tasks = []
    skipped = []
    for idx, task in enumerate(tasks, 1):
        name = task.get("name", f"task_{idx}")
        if not task.get("enabled", True):
            batch_logger.info(f"[{idx}/{total}] ⏭ 跳过（disabled）: {name}")
            skipped.append(name)
            continue
        if args.task and name != args.task:
            batch_logger.info(f"[{idx}/{total}] ⏭ 跳过（非指定任务）: {name}")
            skipped.append(name)
            continue
        run_tasks.append((idx, task, name))

    batch_logger.info(
        f"多任务模式启动：待执行 {len(run_tasks)}，跳过 {len(skipped)}，总计 {total}"
    )

    succeeded = []
    failed = []

    for idx, task, name in run_tasks:
        batch_logger.info(f"[{idx}/{total}] 🚀 开始: {name}")

        # 合并 base + task（去掉辅助字段）
        task_clean = {
            k: v for k, v in task.items() if k not in ("name", "enabled")
        }
        merged = deep_merge(base_dict, task_clean)
        config = Config(merged)

        try:
            run_single_task(
                config, force_regenerate=args.force, batch_logger=batch_logger
            )
            batch_logger.info(f"[{idx}/{total}] ✅ 完成: {name}")
            succeeded.append(name)
        except Exception as e:
            batch_logger.error(
                f"[{idx}/{total}] ❌ 失败: {name} -> {e}", exc_info=True
            )
            failed.append(name)
            # 错误隔离：继续执行下一个
            continue

    # ---------- 汇总 ----------
    batch_logger.info("=" * 60)
    batch_logger.info(
        f"全部任务完成: 成功 {len(succeeded)} | 失败 {len(failed)} | 跳过 {len(skipped)}"
    )
    if succeeded:
        batch_logger.info(f"  ✅ 成功: {succeeded}")
    if failed:
        batch_logger.error(f"  ❌ 失败: {failed}")
    if skipped:
        batch_logger.info(f"  ⏭  跳过: {skipped}")
    batch_logger.info("=" * 60)

    # 有失败任务时返回非零退出码，便于 CI 判断
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()