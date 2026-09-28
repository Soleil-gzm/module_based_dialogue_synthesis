"""
case 自动生成模块

封装 scripts_general/case_generator/case_generator/generators/ 下的各业务线生成器，
供 main.py 在加载案例前按 yaml 开关自动调用。

公开接口：
    generate_cases_if_needed(...) -> bool
    返回 True 表示已生成（或本次触发生成）；False 表示跳过。

输出文件规则（与原 case_generator/run.py 一致）：
    system_dir/case_{n}.txt   —— system prompt 文件
    replace_dir/case_{n}.txt  —— replace 占位数据文件
    n 从 1 开始编号（testify 段从 testify.start 开始）

缓存机制：
    若 system_dir 和 replace_dir 中已有 case 文件数 >= total_cases，
    且未强制重新生成（force_regenerate=False），则直接复用，跳过生成。
    这样 yaml 中 case_auto_generate.enabled=true 默认也不会反复重生成。
"""

import importlib.util
import logging
import os
from typing import Optional

logger = logging.getLogger("DialogueBuilder")

# case_generator/generators 子模块目录（固定相对位置）
_GENERATORS_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "case_generator",
        "case_generator",
        "generators",
    )
)

# 支持的生成器类型（与 GENERATORS 映射的 key 一致）
SUPPORTED_GENERATORS = [
    "m0",
    "m0_follow",
    "m1",
    "m1_follow",
    "m2",
    "m2_follow",
    "m3_plus",
    "m3_plus_follow",
    "suning_backend",
]


def _load_generator_module(generator_type: str):
    """用 importlib 显式加载单个生成器模块，避免触发 generators/__init__.py 的批量导入。"""
    if generator_type not in SUPPORTED_GENERATORS:
        raise ValueError(
            f"不支持的生成器类型: {generator_type}。"
            f"支持的类型: {SUPPORTED_GENERATORS}"
        )
    file_path = os.path.join(_GENERATORS_DIR, f"{generator_type}.py")
    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"生成器文件不存在: {file_path}。"
            f"请确认 scripts_general/case_generator/case_generator/generators/ 完整。"
        )
    spec = importlib.util.spec_from_file_location(
        f"case_generator_{generator_type}", file_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _count_existing_cases(dir_path: str) -> int:
    """统计目录中 case_*.txt 文件数量（不含扩展名）。
    用文件名 case_N.txt 的模式匹配，与生成器输出命名一致。
    """
    if not os.path.isdir(dir_path):
        return 0
    count = 0
    for fname in os.listdir(dir_path):
        if not fname.endswith(".txt"):
            continue
        stem = os.path.splitext(fname)[0]
        # 形如 case_123
        if stem.startswith("case_") and stem[len("case_"):].isdigit():
            count += 1
    return count


def _build_generator_config(
    generator_type: str,
    seed: int,
    total_cases: int,
    system_dir: str,
    replace_dir: str,
    prompt_system_path: str,
    prompt_replace_path: str,
    combinations_path: Optional[str] = None,
    name: Optional[str] = None,
    testify: Optional[dict] = None,
) -> dict:
    """构造与 case_generator/generators/{type}.generate(cfg) 兼容的配置 dict。

    combinations_path 为空时使用默认路径：
        packages/combinations/combinations-auto-{generator_type}-{total_cases}.json
    （生成器内部 generate() 会调用 save_mask_combinations，combinations_path 是必填字段）
    """
    if not combinations_path:
        combinations_path = (
            f"packages/combinations/"
            f"combinations-auto-{generator_type}-{total_cases}.json"
        )
    cfg = {
        "name": name or generator_type,
        "enabled": True,
        "seed": seed,
        "total_cases": total_cases,
        "system_dir": system_dir,
        "replace_dir": replace_dir,
        "prompt_system_path": prompt_system_path,
        "prompt_replace_path": prompt_replace_path,
        "combinations_path": combinations_path,
    }
    if testify:
        cfg["testify"] = testify
    return cfg


def generate_cases_if_needed(
    generator_type: str,
    seed: int,
    total_cases: int,
    system_dir: str,
    replace_dir: str,
    prompt_system_path: str,
    prompt_replace_path: str,
    combinations_path: Optional[str] = None,
    testify: Optional[dict] = None,
    force_regenerate: bool = False,
) -> bool:
    """
    按需生成 case 文件到 system_dir 和 replace_dir。

    若两个目录中已有 case 文件数 >= total_cases，则视为缓存命中，跳过生成。
    若 force_regenerate=True，则忽略缓存强制重新生成。

    Args:
        generator_type: 生成器类型（m0/m0_follow/m1/.../suning_backend）
        seed: 随机种子（一般来自 yaml 的 random_seed）
        total_cases: 要生成的 case 数量
        system_dir: system prompt 输出目录（即 case_loader.system_dir）
        replace_dir: replace 占位数据输出目录（即 case_loader.replace_dir）
        prompt_system_path: system prompt 模板文件路径
        prompt_replace_path: replace prompt 模板文件路径
        combinations_path: mask 组合文件路径（可选）
        testify: 作证 case 配置（可选 dict，含 system_dir/replace_dir/start/end/seed）
        force_regenerate: 强制重新生成

    Returns:
        True 表示本次触发生成或缓存命中（可继续使用现有 case）；
        False 表示因配置问题跳过。
    """
    if not prompt_system_path or not os.path.exists(prompt_system_path):
        raise FileNotFoundError(
            f"system prompt 模板文件不存在: {prompt_system_path}"
        )
    if not prompt_replace_path or not os.path.exists(prompt_replace_path):
        raise FileNotFoundError(
            f"replace prompt 模板文件不存在: {prompt_replace_path}"
        )

    # ---- 缓存检查：已有足够 case 则跳过 ----
    if not force_regenerate:
        existing_system = _count_existing_cases(system_dir)
        existing_replace = _count_existing_cases(replace_dir)
        existing = min(existing_system, existing_replace)
        if existing >= total_cases:
            logger.info(
                f"case 缓存命中：{system_dir} 和 {replace_dir} "
                f"中已有 {existing} 个 case（需 {total_cases}），跳过生成。"
                f"如需强制重新生成，请设 case_auto_generate.force_regenerate=true"
            )
            return True

    # ---- 构造配置并调用生成器 ----
    cfg = _build_generator_config(
        generator_type=generator_type,
        seed=seed,
        total_cases=total_cases,
        system_dir=system_dir,
        replace_dir=replace_dir,
        prompt_system_path=prompt_system_path,
        prompt_replace_path=prompt_replace_path,
        combinations_path=combinations_path,
        name=generator_type,
        testify=testify,
    )

    logger.info("=" * 60)
    logger.info("自动生成 case")
    logger.info(f"  生成器类型:     {generator_type}")
    logger.info(f"  随机种子:       {seed}")
    logger.info(f"  case 数量:      {total_cases}")
    logger.info(f"  system_dir:     {system_dir}")
    logger.info(f"  replace_dir:    {replace_dir}")
    logger.info(f"  prompt_system:  {prompt_system_path}")
    logger.info(f"  prompt_replace: {prompt_replace_path}")
    if combinations_path:
        logger.info(f"  combinations:   {combinations_path}")
    if testify:
        logger.info(f"  testify 配置:   {testify}")
    if force_regenerate:
        logger.info(f"  强制重新生成:   True")
    logger.info("=" * 60)

    # 确保输出目录存在（生成器内部也会 makedirs，提前创建便于日志诊断）
    os.makedirs(system_dir, exist_ok=True)
    os.makedirs(replace_dir, exist_ok=True)

    # 显式加载生成器模块（避免批量导入）
    gen_module = _load_generator_module(generator_type)
    if not hasattr(gen_module, "generate"):
        raise AttributeError(
            f"生成器模块 '{generator_type}' 缺少 generate(cfg) 函数"
        )

    # 调用生成器
    gen_module.generate(cfg)
    logger.info(f"case 生成完成，共 {total_cases} 条")

    return True
