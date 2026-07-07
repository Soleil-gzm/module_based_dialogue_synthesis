"""
Step 1：提取配置到 YAML 文件
操作：创建 configs/general.yaml，将所有硬编码常量（MODULES, MAX_REPEAT, A_SET, B_SET, TERMINAL_NODES, INSERT_NODES, PRESSURE_PROB 等）写入 YAML。
原因：配置与代码分离后，切换公司只需换配置文件，无需改代码。同时便于非开发人员调整参数。

Step 2：定义配置加载器
操作：创建 core/config.py，提供 load_config() 函数，返回一个 Config 对象（或字典）。
原因：统一配置访问入口，后续组件只需依赖这个 Config 对象。

Step 3：自动从 Excel 话术模板提取 max_repeat 和 modules
操作：在 load_config() 后调用 auto_sync_config_from_excel()，自动同步配置。
原因：避免切换话术模板时忘记更新 max_repeat 和 modules 配置。
"""

import logging
import os
import re
from typing import Any, Dict, List, Tuple

import pandas as pd
import yaml

from .exceptions import ConfigError, DataLoadError

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
        raise ConfigError(f"配置文件不存在: {config_path}")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"配置文件解析错误: {config_path}, 错误: {e}")
    if data is None:
        raise ConfigError(f"配置文件为空: {config_path}")
    return Config(data)


def extract_modules_and_max_repeat_from_excel(
    excel_path: str,
    exclude_sheets: List[str] = None,
) -> Tuple[List[str], Dict[str, int]]:
    """
    从 Excel 话术模板中自动提取 modules 列表和 max_repeat 配置。

    Args:
        excel_path: Excel 话术模板文件路径
        exclude_sheets: 需要排除的 sheet 名列表（如 '链接施压话术'、'逻辑'）

    Returns:
        (modules, max_repeat): 模块列表和最大重复次数字典
    """
    if not os.path.exists(excel_path):
        logger.warning(f"话术模板文件不存在: {excel_path}，跳过自动提取")
        return [], {}

    # 默认排除不参与对话生成的特殊模块
    if exclude_sheets is None:
        exclude_sheets = ["链接施压话术", "逻辑"]

    # 获取所有 sheet 名，排除特殊模块
    xls = pd.ExcelFile(excel_path)
    modules = [sheet for sheet in xls.sheet_names if sheet not in exclude_sheets]

    # 提取每个模块的 max_repeat（取 repeat(次数) 列的最大值）
    max_repeat = {}
    for module in modules:
        try:
            df = pd.read_excel(excel_path, sheet_name=module)
            if "repeat(次数)" in df.columns:
                # 解析每个 repeat 值，支持范围格式（如 1/2）
                parsed_values = df["repeat(次数)"].apply(_parse_repeat_value)
                max_val = int(parsed_values.max())
                if max_val > 0:
                    max_repeat[module] = max_val
                else:
                    max_repeat[module] = 1  # 默认值
                    logger.warning(
                        f"模块 '{module}' 的 repeat(次数) 列最大值为0，使用默认值 1"
                    )
            else:
                max_repeat[module] = 1  # 默认值
                logger.warning(
                    f"模块 '{module}' 缺少 'repeat(次数)' 列，使用默认值 1"
                )
        except Exception as e:
            logger.warning(f"读取模块 '{module}' 的 repeat(次数) 失败: {e}")
            max_repeat[module] = 1

    xls.close()
    return modules, max_repeat


def auto_sync_config_from_excel(config: Config) -> Config:
    """
    自动从 Excel 话术模板同步 modules 和 max_repeat 配置到 Config 对象。

    比较 Excel 提取值与 YAML 配置值，如果有差异则打印警告并使用 Excel 的值。

    Args:
        config: 原始 Config 对象

    Returns:
        更新后的 Config 对象
    """
    excel_path = config.get("excel_path")
    if not excel_path or not os.path.exists(excel_path):
        logger.warning(
            f"话术模板文件不存在: {excel_path}，跳过自动同步 modules 和 max_repeat"
        )
        return config

    # 从 Excel 提取
    excel_modules, excel_max_repeat = extract_modules_and_max_repeat_from_excel(
        excel_path
    )
    if not excel_modules:
        return config

    config_dict = config.to_dict()
    yaml_modules = config_dict.get("modules", [])
    yaml_max_repeat = config_dict.get("max_repeat", {})

    # 同步 modules
    if set(excel_modules) != set(yaml_modules):
        logger.warning("=" * 60)
        logger.warning("检测到 modules 配置与话术模板不一致，自动使用话术模板的 modules")
        logger.warning(f"  话术模板 modules 数量: {len(excel_modules)}")
        logger.warning(f"  YAML 配置 modules 数量: {len(yaml_modules)}")

        # 找出差异
        only_in_excel = set(excel_modules) - set(yaml_modules)
        only_in_yaml = set(yaml_modules) - set(excel_modules)
        if only_in_excel:
            logger.warning(f"  仅在话术模板中: {only_in_excel}")
        if only_in_yaml:
            logger.warning(f"  仅在YAML配置中: {only_in_yaml}")
        logger.warning("=" * 60)

        config_dict["modules"] = excel_modules

    # 同步 max_repeat
    updated_max_repeat = {}
    max_repeat_diff = {}
    for module in excel_modules:
        excel_val = excel_max_repeat.get(module, 1)
        yaml_val = yaml_max_repeat.get(module)

        if yaml_val is None:
            # YAML 中没有配置，使用 Excel 的值
            updated_max_repeat[module] = excel_val
            max_repeat_diff[module] = ("未配置", excel_val)
        elif yaml_val != excel_val:
            # 值不同，使用 Excel 的值
            updated_max_repeat[module] = excel_val
            max_repeat_diff[module] = (yaml_val, excel_val)
        else:
            # 值相同，保持原值
            updated_max_repeat[module] = yaml_val

    if max_repeat_diff:
        logger.warning("=" * 60)
        logger.warning("检测到 max_repeat 配置与话术模板不一致，自动使用话术模板的值")
        for module, (yaml_val, excel_val) in max_repeat_diff.items():
            logger.warning(f"  {module}: YAML={yaml_val} -> Excel={excel_val}")
        logger.warning("=" * 60)

        config_dict["max_repeat"] = updated_max_repeat

    return Config(config_dict)
