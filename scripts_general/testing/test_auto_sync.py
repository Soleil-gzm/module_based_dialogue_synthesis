#!/usr/bin/env python3
"""
测试自动从 Excel 话术模板同步 modules 和 max_repeat 配置的功能
"""

import sys
import logging

sys.path.insert(0, "scripts_general")

from core.config import load_config, sync_config_from_prob
from core.data_loader import load_prob_matrix

# 配置日志以查看警告信息
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s - %(message)s"
)


def test_auto_sync():
    # 加载配置
    config_path = "configs/general_Xiaoying_0701_1w.yaml"
    print(f"加载配置文件: {config_path}")
    config = load_config(config_path)

    # 查看原始配置
    print("\n" + "=" * 60)
    print("原始配置（从 YAML 读取）")
    print("=" * 60)
    print(f"modules 数量: {len(config.get('modules', []))}")
    print(f"max_repeat 配置数量: {len(config.get('max_repeat', {}))}")

    # 加载 prob 表 → 提取 modules
    print("\n" + "=" * 60)
    print("加载 prob 表，提取 modules")
    print("=" * 60)
    prob_df, modules = load_prob_matrix(config.get("prob_path"))
    print(f"prob 表 modules 数量: {len(modules)}")

    # 以 modules 为准，从 Excel 同步 max_repeat
    print("\n" + "=" * 60)
    print("执行同步（prob 表 modules + Excel max_repeat）")
    print("=" * 60)
    config = sync_config_from_prob(config, modules)

    # 查看同步后的配置
    print("\n" + "=" * 60)
    print("同步后的配置")
    print("=" * 60)
    print(f"modules 数量: {len(config.get('modules', []))}")
    print(f"max_repeat 配置数量: {len(config.get('max_repeat', {}))}")
    
    # 显示部分 max_repeat 值
    max_repeat = config.get('max_repeat', {})
    print("\n部分模块的 max_repeat 值：")
    for module in list(max_repeat.keys())[:5]:
        print(f"  {module}: {max_repeat[module]}")
    
    print("\n测试完成！")


if __name__ == "__main__":
    test_auto_sync()
