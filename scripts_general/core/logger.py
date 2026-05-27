'''
Step 10：添加错误处理与日志统一
操作：使用 logging 模块，配置文件日志和控制台日志；在关键步骤添加 try-except，记录失败路径信息。
原因：提高健壮性，便于定位问题。
'''
'''
四、注意事项与最佳实践
不要在每个文件中创建新的 logger 实例：统一使用 get_logger()。

避免重复添加处理器：上面的代码通过 _logger_instance 全局单例保证了只初始化一次。

可测试性：在单元测试中，你可以通过 logging.getLogger("DialogueBuilder").handlers.clear() 清空处理器，或替换为 unittest.mock。

多模块共享：所有使用 get_logger() 的地方获得的都是同一个 logger 对象，因此日志输出会汇总到同一个文件（按时间戳分隔）。

按日期切割日志：如果需要按天滚动，可以使用 logging.handlers.TimedRotatingFileHandler 替代 FileHandler。

敏感信息处理：避免在日志中打印客户真实姓名、手机号等敏感数据，或使用 logging.Filter 脱敏。
'''

import logging
import os
from datetime import datetime
from typing import Optional

_logger_instance: Optional[logging.Logger] = None

def init_logger(config) -> logging.Logger:
    """
    根据配置初始化logger（应在程序启动时调用一次）
    config: Config对象或字典
    """
    global _logger_instance
    if _logger_instance is not None:
        return _logger_instance

    # 获取日志配置
    if hasattr(config, 'get'):
        log_config = config.get('logging', {})
    else:
        log_config = config.get('logging', {})

    level_name = log_config.get('level', 'INFO').upper()
    level = getattr(logging, level_name, logging.INFO)
    log_dir = log_config.get('log_dir', 'logs')
    file_prefix = log_config.get('file_prefix', 'app')
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
    _logger_instance = logger
    return logger

def get_logger() -> logging.Logger:
    """获取已初始化的logger，若未初始化则使用默认配置"""
    if _logger_instance is None:
        # 使用默认配置初始化
        default_config = {'logging': {'level': 'INFO', 'log_dir': 'logs', 'file_prefix': 'default'}}
        init_logger(default_config)
    return _logger_instance