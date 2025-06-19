"""
日志管理模块
"""

import os
import sys
import logging
import logging.handlers
from datetime import datetime
from typing import Optional


class LoggerManager:
    """日志管理器"""

    _instance = None
    _logger = None
    _log_buffer = []  # 日志缓冲区
    _max_buffer_size = 1000  # 最大缓冲区大小

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_logger(cls) -> logging.Logger:
        """获取日志实例"""
        if cls._logger is None:
            cls._logger = setup_logger()
        return cls._logger

    @classmethod
    def add_log(cls, level: str, message: str):
        """添加日志到缓冲区"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'message': message
        }

        cls._log_buffer.append(log_entry)

        # 限制缓冲区大小
        if len(cls._log_buffer) > cls._max_buffer_size:
            cls._log_buffer.pop(0)

    @classmethod
    def get_logs(cls, limit: int = 100) -> list:
        """获取最近的日志"""
        return cls._log_buffer[-limit:]

    @classmethod
    def clear_logs(cls):
        """清空日志缓冲区"""
        cls._log_buffer.clear()


class BufferedLogHandler(logging.Handler):
    """缓冲日志处理器"""

    def emit(self, record):
        """处理日志记录"""
        try:
            msg = self.format(record)
            LoggerManager.add_log(record.levelname, msg)
        except Exception:
            self.handleError(record)


def setup_logger(name: str = "netflix_checker",
                 log_file: Optional[str] = None) -> logging.Logger:
    """设置日志"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 清除已有的处理器
    logger.handlers.clear()

    # 格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    if log_file is None:
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{name}.log")

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 缓冲处理器
    buffer_handler = BufferedLogHandler()
    buffer_handler.setLevel(logging.INFO)
    buffer_handler.setFormatter(formatter)
    logger.addHandler(buffer_handler)

    return logger