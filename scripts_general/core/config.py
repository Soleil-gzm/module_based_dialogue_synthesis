'''
Step 1：提取配置到 YAML 文件
操作：创建 config/general.yaml，将所有硬编码常量（MODULES, MAX_REPEAT, A_SET, B_SET, TERMINAL_NODES, INSERT_NODES, PRESSURE_PROB 等）写入 YAML。
原因：配置与代码分离后，切换公司只需换配置文件，无需改代码。同时便于非开发人员调整参数。

Step 2：定义配置加载器
操作：创建 core/config.py，提供 load_config() 函数，返回一个 Config 对象（或字典）。
原因：统一配置访问入口，后续组件只需依赖这个 Config 对象。
'''
import yaml
import os
from typing import Any, Dict

class Config:
    """配置类，保存所有配置参数"""
    def __init__(self, config_dict: Dict[str, Any]):
        self._data = config_dict

    def get(self, key: str, default=None):
        """支持点号分隔的嵌套访问，如 'logging.level'"""
        keys = key.split('.')
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
    with open(config_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return Config(data)
