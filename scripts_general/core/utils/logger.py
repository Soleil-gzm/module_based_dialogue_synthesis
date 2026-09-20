import logging
import os
from datetime import datetime
from typing import Optional

# 模块级全局变量，整个模块内只有一个实例，用于实现单例模式
_logger_instance: Optional[logging.Logger] = None


def init_logger(config, log_dir: str = None, timestamp: str = None) -> logging.Logger:
    """
    根据配置初始化logger（应在程序启动时调用一次）
    config: Config对象或字典
    log_dir: 可选的日志目录（若为None则从config中读取）
    timestamp: 可选的时间戳，用于统一命名
    """
    global _logger_instance
    if _logger_instance is not None:
        return _logger_instance

    # 获取日志配置
    log_config = config.get("logging", {})
    level_name = log_config.get("level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    file_prefix = log_config.get("file_prefix", "dialogue_builder")
    console_enabled = log_config.get("console", True)
    fmt = log_config.get(
        "format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    datefmt = log_config.get("datefmt", "%Y-%m-%d %H:%M:%S")

    # 确定日志目录
    if log_dir is None:
        log_dir = log_config.get("log_dir", "logs")
    os.makedirs(log_dir, exist_ok=True)

    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"{file_prefix}_{timestamp}.log")

    logger = logging.getLogger("DialogueBuilder")
    logger.setLevel(level)

    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_formatter = logging.Formatter(fmt, datefmt)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    if console_enabled:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(fmt, datefmt)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    logger.propagate = False
    _logger_instance = logger
    return logger


def get_logger() -> logging.Logger:
    """获取已初始化的logger，若未初始化则使用默认配置"""
    if _logger_instance is None:
        # 使用默认配置初始化
        default_config = {
            "logging": {"level": "INFO", "log_dir": "logs", "file_prefix": "default"}
        }
        init_logger(default_config)
    return _logger_instance
