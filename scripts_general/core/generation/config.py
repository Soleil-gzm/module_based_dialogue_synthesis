"""
配置加载与同步模块（calamine 引擎版 + 多任务支持）。

数据来源优先级：
  1. prob 表（模块转移概率矩阵）→ modules 的唯一来源
  2. Excel 话术模板 → max_repeat 的默认来源
  3. YAML 配置 → 仅用于覆盖/约束（start_module, terminal_modules, a_set, b_set 等）

调用顺序：load_config() → load_prob_matrix() 得到 modules → sync_config_from_prob()

多任务支持：
  - load_tasks_config() 从 tasks_*.yaml 读取 base + 任务列表
  - deep_merge() 递归合并 base 与单个任务
"""

import logging
import os
import re
from typing import Any, Dict, List, Tuple

import pandas as pd
import yaml

logger = logging.getLogger("DialogueBuilder")


# ============================================================
# 1. 基础工具
# ============================================================
def _parse_repeat_value(value) -> int:
    """
    解析 repeat(次数) 列的值，支持以下格式：
    - 单个数字：3 -> 3
    - 多值分隔：1/2/3 -> 3（取最大值）
    - 范围值：1-3 -> 3（取最大值）
    - 空值/NaN -> 1（默认值）
    """
    if pd.isna(value):
        return 1

    value_str = str(value).strip()
    parts = re.split(r"[\s/;,\\-]+", value_str)

    numbers = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        match = re.search(r"(\d+)", part)
        if match:
            numbers.append(int(match.group(1)))

    if numbers:
        return max(numbers)

    logger.warning(f"无法解析 repeat 值: '{value_str}'，使用默认值 1")
    return 1


class Config:
    """配置类，保存所有配置参数"""

    def __init__(self, config_dict: Dict[str, Any]):
        self._data = config_dict

    def get(self, key: str, default=None):
        """支持点号分隔的嵌套访问，如 'logging.level'"""
        keys = key.split(".")
        value = self._data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def __getattr__(self, name: str):
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"Config has no attribute '{name}'")

    def to_dict(self) -> Dict:
        return self._data.copy()


# ============================================================
# 2. YAML 加载
# ============================================================
def load_config(config_path: str) -> Config:
    """加载单个 YAML 配置文件并返回 Config 对象（向后兼容）。"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Config(data)


def deep_merge(base: dict, override: dict) -> dict:
    """
    递归合并两个字典：
    - dict + dict → 递归合并
    - 其他类型（list、标量）→ override 直接覆盖 base

    返回一个新的字典，不修改原字典。
    """
    result = base.copy()
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _resolve_base_path(base_rel, config_path: str) -> str:
    """
    将 base 字段解析为绝对路径（相对当前配置文件目录）。
    支持 str 或 list[str]（多 base 依次合并，后者覆盖前者）。
    """
    if isinstance(base_rel, list):
        # 返回列表时，后续在 load_tasks_config 中处理
        return base_rel
    if os.path.isabs(base_rel):
        return base_rel
    return os.path.join(os.path.dirname(config_path), base_rel)


def load_tasks_config(
    config_path: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    加载多任务配置文件。

    返回 (base_dict, tasks_list)：
    - base_dict: 基础配置（dict），由 `base` 字段指向的 YAML 加载而来
    - tasks_list: 任务列表（每个元素是 dict）

    若配置文件不含 `tasks` 字段，返回 ({}, [])，调用方应回退到 load_config()。
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if "tasks" not in raw:
        return {}, []

    base_rel = raw.pop("base", None)
    base_dict: Dict[str, Any] = {}

    if base_rel:
        # 支持单个 base 或 base 列表（多个 base 依次合并）
        base_paths = base_rel if isinstance(base_rel, list) else [base_rel]
        for bp in base_paths:
            bp = _resolve_base_path(bp, config_path)
            if not os.path.exists(bp):
                raise FileNotFoundError(f"基础配置文件不存在: {bp}")
            with open(bp, "r", encoding="utf-8") as f:
                base_dict = deep_merge(base_dict, yaml.safe_load(f) or {})

    tasks = raw.get("tasks") or []
    if not isinstance(tasks, list):
        raise ValueError(f"'tasks' 字段必须是列表，实际为: {type(tasks)}")

    return base_dict, tasks


# ============================================================
# 3. 从 Excel 提取 max_repeat
# ============================================================
def extract_max_repeat_from_excel(
    excel_path: str,
    modules: List[str],
) -> Dict[str, int]:
    """
    从 Excel 话术模板提取指定模块的 max_repeat（取 repeat(次数) 列最大值）。
    modules 由 prob 表提供，本函数只负责读取 max_repeat。

    使用 calamine 引擎，天然免疫损坏的 AutoFilter。
    """
    if not os.path.exists(excel_path):
        logger.warning(f"话术模板文件不存在: {excel_path}，跳过 max_repeat 提取")
        return {}

    max_repeat = {}
    for module in modules:
        try:
            df = pd.read_excel(excel_path, sheet_name=module, engine="calamine")
            if "repeat(次数)" in df.columns:
                parsed_values = df["repeat(次数)"].apply(_parse_repeat_value)
                max_val = int(parsed_values.max())
                if max_val > 0:
                    max_repeat[module] = max_val
                else:
                    max_repeat[module] = 1
                    logger.warning(
                        f"模块 '{module}' 的 repeat(次数) 列最大值为0，使用默认值 1"
                    )
            else:
                max_repeat[module] = 1
                logger.warning(f"模块 '{module}' 缺少 'repeat(次数)' 列，使用默认值 1")
        except Exception as e:
            logger.warning(f"读取模块 '{module}' 的 repeat(次数) 失败: {e}")
            max_repeat[module] = 1
    return max_repeat


# ============================================================
# 4. 从 prob 同步配置
# ============================================================
def sync_config_from_prob(config: Config, prob_modules: List[str]) -> Config:
    """
    以 prob 表 modules 为准，从 Excel 提取 max_repeat，YAML 可覆盖。

    - modules: 直接来自 prob 表（唯一来源）
    - max_repeat: Excel 默认值，YAML 中显式配置的模块可覆盖

    Args:
        config: 原始 Config 对象
        prob_modules: 从 prob 表提取的模块列表

    Returns:
        更新后的 Config 对象
    """
    config_dict = config.to_dict()

    # modules 直接来自 prob 表
    yaml_modules = config_dict.get("modules", [])
    if yaml_modules and set(yaml_modules) != set(prob_modules):
        logger.warning("=" * 60)
        logger.warning("modules 已由 prob 表自动提取，YAML 配置值将被覆盖")
        logger.warning(f"  prob 表 modules 数量: {len(prob_modules)}")
        logger.warning(f"  YAML 配置 modules 数量: {len(yaml_modules)}")
        only_in_prob = set(prob_modules) - set(yaml_modules)
        only_in_yaml = set(yaml_modules) - set(prob_modules)
        if only_in_prob:
            logger.warning(f"  仅在 prob 表中: {only_in_prob}")
        if only_in_yaml:
            logger.warning(f"  仅在 YAML 中: {only_in_yaml}")
        logger.warning("=" * 60)
    config_dict["modules"] = prob_modules

    # max_repeat: Excel 是唯一来源，YAML 配置不一致时仅提醒（不覆盖）
    excel_path = config.get("excel_path")
    excel_max_repeat = extract_max_repeat_from_excel(excel_path, prob_modules)
    yaml_max_repeat = config_dict.get("max_repeat") or {}

    diff = {}
    for module, yaml_val in yaml_max_repeat.items():
        if module in excel_max_repeat and yaml_val != excel_max_repeat[module]:
            diff[module] = (excel_max_repeat[module], yaml_val)

    config_dict["max_repeat"] = excel_max_repeat

    if diff:
        logger.warning("=" * 60)
        logger.warning("max_repeat YAML 配置与 Excel 不一致（已使用 Excel 的值）")
        for module, (excel_val, yaml_val) in diff.items():
            logger.warning(f"  {module}: Excel={excel_val}, YAML={yaml_val}")
        logger.warning("  如需修改 max_repeat，请直接修改 Excel 的 repeat(次数) 列")
        logger.warning("=" * 60)
    return Config(config_dict)