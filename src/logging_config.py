import logging
import logging.handlers
from pathlib import Path


def setup_logging(log_level: str = "INFO", log_dir: str = "logs", log_file: str = "pataphaw-jr.log"):
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_path / log_file,
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    formatter = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)