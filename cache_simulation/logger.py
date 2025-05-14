import logging
from logging.handlers import RotatingFileHandler

from cache_simulation.config import Settings


def setup_logging(settings: Settings):
    """
    Настройка логгера на основе pydantic-модели Settings.logging.
    """
    log_cfg = settings.logging

    # уровни
    console_level = logging.getLevelName(log_cfg.console.level.upper())
    file_level = logging.getLevelName(log_cfg.file.level.upper())

    root = logging.getLogger()
    root.setLevel(min(console_level, file_level))

    # консоль
    ch = logging.StreamHandler()
    ch.setLevel(console_level)
    ch.setFormatter(logging.Formatter(log_cfg.console.fmt, datefmt=log_cfg.date_format))
    root.addHandler(ch)

    # файл с ротацией
    fh = RotatingFileHandler(
        filename=log_cfg.file.path,
        maxBytes=log_cfg.file.max_bytes,
        backupCount=log_cfg.file.backup_count,
        encoding="utf-8"
    )
    fh.setLevel(file_level)
    fh.setFormatter(logging.Formatter(log_cfg.file.fmt, datefmt=log_cfg.date_format))
    root.addHandler(fh)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
