"""
并行对话生成器：统一单进程/多进程调度，支持断点续传。

将分片切分、断点检查、任务派发、分片合并等编排逻辑封装于此，
使 main.py 仅负责配置加载与数据准备。
"""

import json
import os
import multiprocessing as mp
from typing import List, Optional, Tuple

from tqdm import tqdm

from core.config import Config
from core.dialogue_builder import DialogueBuilder
from core.pressure_manager import PressureManager
from core.random_service import RandomService

# ==================== JSON 序列化（支持 orjson 加速） ====================
try:
    import orjson

    USE_ORJSON = True
except ImportError:
    USE_ORJSON = False


def dumps_json(obj) -> str:
    """序列化 JSON 对象，支持 orjson 加速"""
    if USE_ORJSON:
        return orjson.dumps(obj, option=orjson.OPT_SERIALIZE_NUMPY).decode("utf-8")
    return json.dumps(obj, ensure_ascii=False)


# ==================== 辅助函数 ====================
def count_jsonl_lines(filepath: str) -> int:
    """统计 JSONL 文件的行数（用于判断分片是否完整）"""
    if not os.path.exists(filepath):
        return 0
    count = 0
    with open(filepath, "r", encoding="utf-8") as f:
        for _ in f:
            count += 1
    return count


# ==================== Worker 函数 ====================
def worker_generate(
    start_idx: int,
    end_idx: int,
    output_file: str,
    trace_file: Optional[str],
    config_dict: dict,
    all_paths: list,
    cases: list,
    prompts: list,
    df_dict: dict,
    pressure_df,
    seed: int,
    process_id: int,
    trace_enabled: bool,
    checkpoint_interval: int,
    already_done: int = 0,
) -> int:
    """
    子进程任务：生成对话并写入分片文件（JSON Lines），同时收集 trace（若启用）。
    支持断点续传：already_done 表示已完成的数量，从 start_idx + already_done 开始继续。
    """
    import sys

    config = Config(config_dict)
    rng = RandomService(seed + process_id)  # 独立种子
    pressure_manager = PressureManager(pressure_df, rng, config)
    builder = DialogueBuilder(
        config, df_dict, rng, pressure_manager, None
    )

    total_paths = len(all_paths)
    total_cases = len(cases)

    resume_start = start_idx + already_done  # 判断task完成多少
    total_expected = end_idx - start_idx

    # 已完成全部，直接返回
    if already_done >= total_expected:
        print(f"进程 {process_id} 分片已完成（{already_done}/{total_expected}），跳过")
        return total_expected

    # 追加模式：从断点处继续写入
    mode = "a" if already_done > 0 else "w"
    all_traces: Optional[list] = [] if trace_enabled else None

    # 续传时尝试加载已有 trace
    if trace_enabled and already_done > 0 and trace_file and os.path.exists(trace_file):
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
                    f_out.flush()       # flush() 强制把 Python 缓冲区里的数据写入磁盘。
                if trace_enabled:
                    all_traces.append(builder.get_trace_data())
            except Exception as e:
                print(f"进程 {process_id} 第{i}条对话出错: {e}", file=sys.stderr)
                continue

    if trace_enabled and all_traces is not None and trace_file:
        with open(trace_file, "w", encoding="utf-8") as f_trace:
            json.dump(all_traces, f_trace, ensure_ascii=False, indent=2)

    return end_idx - start_idx


# ==================== 合并分片文件 ====================
def merge_shards_to_json(shard_files: List[str], output_file: str):
    """将多个 JSON Lines 分片合并为一个标准 JSON 数组文件，合并完成后删除分片"""
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

    # 合并成功后删除分片文件
    for shard in shard_files:
        if os.path.exists(shard):
            os.remove(shard)


def merge_trace_shards(shard_files: List[str], output_file: str):
    """合并 trace 分片（每个分片是一个 JSON 列表），合并完成后删除分片"""
    all_traces = []
    for shard in shard_files:
        if os.path.exists(shard) and os.path.getsize(shard) > 0:
            with open(shard, "r", encoding="utf-8") as f:
                traces = json.load(f)
                all_traces.extend(traces)

    with open(output_file, "w", encoding="utf-8") as f_out:
        json.dump(all_traces, f_out, ensure_ascii=False, indent=2)

    # 合并成功后删除分片文件
    for shard in shard_files:
        if os.path.exists(shard):
            os.remove(shard)


# ==================== 统一生成入口 ====================
def generate_dialogues(
    *,
    num_dialogues: int,
    num_processes: int,
    task_dir: str,
    traces_dir: str,
    task_name: str,
    seed: int,
    timestamp: str,
    config_dict: dict,
    all_paths: list,
    cases: list,
    prompts: list,
    df_dict: dict,
    pressure_df,
    trace_enabled: bool,
    checkpoint_interval: int,
    logger,
    force_regenerate: bool = False,
) -> Tuple[str, Optional[str]]:
    """
    统一的对话生成入口（支持单进程/多进程 + 断点续传）。

    Returns:
        (final_output_file, trace_file)
    """
    # 分片切分
    chunk_size = (num_dialogues + num_processes - 1) // num_processes       # 向上取整
    ranges = []
    for p in range(num_processes):
        start = p * chunk_size
        end = min(start + chunk_size, num_dialogues)
        if start < end:
            ranges.append((start, end))

    # 准备分片文件，检查完整性以支持断点续传
    shard_files: List[str] = []
    trace_shard_files: List[str] = []
    tasks = []
    skipped_count = 0
    resumed_count = 0

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
            logger.info(
                f"分片 {p} ({start}-{end}) 已完成（{already_done}/{expected_lines}），跳过"
            )
            if trace_enabled:
                trace_shard = os.path.join(
                    task_dir, f"trace_shard_{p:03d}_{start}_{end}.json"
                )
                trace_shard_files.append(trace_shard)
            continue        # 不加入 tasks

        if already_done > 0:
            resumed_count += 1
            logger.info(
                f"分片 {p} ({start}-{end}) 已完成 {already_done}/{expected_lines}，将续传"
            )

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

    # 任务派发：多进程用 Pool，单进程直接调用
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
        trace_file = os.path.join(
            traces_dir, f"{task_name}_traces_{num_dialogues}_{seed}_{timestamp}.json"
        )
        logger.info("合并 trace 分片...")
        merge_trace_shards(trace_shard_files, trace_file)
        logger.info(f"追踪数据已保存至 {trace_file}")

    logger.info(f"生成完成，共 {num_dialogues} 条对话，保存至 {final_output_file}")

    return final_output_file, trace_file
