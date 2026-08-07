"""
配置加载与同步模块。

数据来源优先级：
  1. prob 表（模块转移概率矩阵）→ modules 的唯一来源
  2. Excel 话术模板 → max_repeat 的默认来源
  3. YAML 配置 → 仅用于覆盖/约束（start_module, terminal_modules, a_set, b_set 等）

调用顺序：load_config() → load_prob_matrix() 得到 modules → sync_config_from_prob()
"""

import logging
import os
import re
from typing import Any, Dict, List, Tuple

import pandas as pd
import yaml

logger = logging.getLogger(__name__)


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
    
    # 转换为字符串
    value_str = str(value).strip()
    
    # 尝试按分隔符（/ 或 - 或 ; 或 ,）拆分
    # 支持多个分隔符，如 1/2/3 或 ;1/2/3 或 1,2,3
    # 注意：- 放在字符类末尾或转义
    parts = re.split(r'[\s/;,\\-]+', value_str)
    
    # 提取所有数字
    numbers = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        match = re.search(r'(\d+)', part)
        if match:
            numbers.append(int(match.group(1)))
    
    if numbers:
        return max(numbers)
    
    # 无法解析，返回默认值
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


def load_config(config_path: str) -> Config:
    """加载YAML配置文件并返回Config对象"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Config(data)


def extract_max_repeat_from_excel(
    excel_path: str,
    modules: List[str],
) -> Dict[str, int]:
    """
    从 Excel 话术模板提取指定模块的 max_repeat（取 repeat(次数) 列最大值）。
    modules 由 prob 表提供，本函数只负责读取 max_repeat。
    """
    if not os.path.exists(excel_path):
        logger.warning(f"话术模板文件不存在: {excel_path}，跳过 max_repeat 提取")
        return {}

    max_repeat = {}
    for module in modules:
        try:
            df = pd.read_excel(excel_path, sheet_name=module)
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
                logger.warning(
                    f"模块 '{module}' 缺少 'repeat(次数)' 列，使用默认值 1"
                )
        except Exception as e:
            logger.warning(f"读取模块 '{module}' 的 repeat(次数) 失败: {e}")
            max_repeat[module] = 1
    return max_repeat


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

    # max_repeat: Excel 默认值，YAML 可覆盖
    excel_path = config.get("excel_path")
    excel_max_repeat = extract_max_repeat_from_excel(excel_path, prob_modules)

    yaml_max_repeat = config_dict.get("max_repeat", {})
    updated_max_repeat = {}
    max_repeat_overrides = {}
    for module in prob_modules:
        excel_val = excel_max_repeat.get(module, 1)
        yaml_val = yaml_max_repeat.get(module)
        if yaml_val is not None:
            # YAML 显式配置，覆盖 Excel 默认值
            updated_max_repeat[module] = yaml_val
            if yaml_val != excel_val:
                max_repeat_overrides[module] = (excel_val, yaml_val)
        else:
            updated_max_repeat[module] = excel_val

    if max_repeat_overrides:
        logger.info("=" * 60)
        logger.info("max_repeat 使用 YAML 覆盖值（其余从 Excel 提取）")
        for module, (excel_val, yaml_val) in max_repeat_overrides.items():
            logger.info(f"  {module}: Excel={excel_val} -> YAML={yaml_val}")
        logger.info("=" * 60)

    config_dict["max_repeat"] = updated_max_repeat
    return Config(config_dict)
