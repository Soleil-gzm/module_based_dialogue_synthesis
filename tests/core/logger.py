import logging
import os
from datetime import datetime
from typing import Optional

# 模块级全局变量，整个模块内只有一个实例，用于实现单例模式
_logger_instance: Optional[logging.Logger] = None

def init_logger(config) -> logging.Logger:
    """
    根据配置初始化logger（应在程序启动时调用一次），保证返回一个配置好的 Logger 对象
    config: Config对象或字典
    """
    global _logger_instance     # 允许函数内部修改模块级全局变量
    # 实现单例模式，防止重复初始化
    if _logger_instance is not None:
        return _logger_instance

    # 获取日志配置
    log_config = config.get('logging', {}) 

    level_name = log_config.get('level', 'INFO').upper()        # 得到 'INFO'（字符串）
    level = getattr(logging, level_name, logging.INFO)          # 得到 logging.INFO（整数 20）
    log_dir = log_config.get('log_dir', 'logs')
    file_prefix = log_config.get('file_prefix', 'general_dialogue_builder')
    console_enabled = log_config.get('console', True)
    fmt = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    datefmt = log_config.get('datefmt', '%Y-%m-%d %H:%M:%S')

    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(log_dir, f"{file_prefix}_{timestamp}.log")

    logger = logging.getLogger('DialogueBuilder')
    logger.setLevel(level)

    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(level)
    file_formatter = logging.Formatter(fmt, datefmt)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # 控制台处理器
    if console_enabled:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(fmt, datefmt)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    logger.propagate = False
    _logger_instance = logger       # 将创建好的 logger 实例保存到模块级全局变量，实现单例
    return logger

def get_logger() -> logging.Logger:
    """获取已初始化的logger，若未初始化则使用默认配置"""
    if _logger_instance is None:
        # 使用默认配置初始化
        default_config = {'logging': {'level': 'INFO', 'log_dir': 'logs', 'file_prefix': 'default'}}
        init_logger(default_config)
    return _logger_instance