"""Structured JSON logger for InfraDocs V6."""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["timestamp"] = datetime.now(timezone.utc).isoformat()
        log_record["level"] = record.levelname
        log_record["module"] = record.module
        log_record["function"] = record.funcName


def setup_logger(
    name: str,
    log_file: str | None = None,
    level: str = "INFO",
    format_type: str = "json",
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    logger.handlers = []

    if format_type == "json":
        formatter = CustomJsonFormatter(
            "%(timestamp)s %(level)s %(module)s %(function)s %(message)s"
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_scan_logger(scan_type: str = "full") -> logging.Logger:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return setup_logger(
        name=f"scan.{scan_type}",
        log_file=f"logs/scan_{scan_type}_{timestamp}.log",
        level="INFO",
        format_type="json",
    )


def get_api_logger() -> logging.Logger:
    return setup_logger(
        name="api",
        log_file="logs/api.log",
        level="INFO",
        format_type="json",
    )
