# src/helpers/logger.py
import logging
import re
import traceback
from enum import Enum
from typing import Optional

from src.utils.startup_arguments import get_startup_arguments


class Status(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"


def _get_default_verbose_level() -> int:
    """Return the configured startup verbose level or fallback to WARNING."""
    try:
        args = get_startup_arguments()
        return int(getattr(args, "verbose_level", 0))
    except Exception:
        return 0


# Ensure logger initialized only once
_logger = logging.getLogger("teachable")
_logger.propagate = False


def _ensure_logger_configured(level: int):
    if not _logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        _logger.addHandler(handler)
    _logger.setLevel(level)


def _sanitize_native_stacktrace(text: str) -> str:
    """
    Remove native 'Stacktrace:' dumps and trailing hex-address lines from exception text.
    Heuristic: if 'Stacktrace:' appears, cut everything from that token onward.
    Also strip long runs of hex-address lines (e.g. lines starting with 0x...).
    """
    if not text:
        return text
    # If 'Stacktrace:' present, drop it and everything after.
    idx = text.find("Stacktrace:")
    if idx != -1:
        text = text[:idx].rstrip()

    # Remove lines that look like unresolved backtrace (e.g. 0x7ff71833a235)
    cleaned_lines = []
    for line in text.splitlines():
        # If line is mostly hex addresses (with optional whitespace and tabs), skip it
        if re.match(r"^\s*0x[0-9a-fA-F]{6,}", line):
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines).strip()
    return cleaned


def log(
    message: str,
    status: Status = Status.INFO,
    verbose_level: int = -1,
    exc: Optional[Exception] = None,
    exc_info: bool = False,
):
    """
    Improved logging with traceback sanitization.

    - exc: pass an Exception object to print its traceback (sanitized).
    - exc_info=True: prints the current exception traceback (inside except).
    """

    # Decide verbosity -> numeric logging level
    if verbose_level in {0, 1, 2}:
        log_level = [logging.WARNING, logging.INFO, logging.DEBUG][verbose_level]
    else:
        default_lvl = _get_default_verbose_level()
        log_level = [logging.WARNING, logging.INFO, logging.DEBUG][
            min(max(default_lvl, 0), 2)
        ]

    _ensure_logger_configured(log_level)

    # Map status -> logging level
    if status == Status.ERROR:
        level = logging.ERROR
    elif status == Status.WARNING:
        level = logging.WARNING
    elif status == Status.DEBUG:
        level = logging.DEBUG
    else:
        level = logging.INFO

    final_message = message or ""

    # If exc_info True: append current traceback (format_exc), sanitized
    if exc_info:
        try:
            tb_text = traceback.format_exc()
            tb_text = _sanitize_native_stacktrace(tb_text)
            if tb_text and "NoneType: None" not in tb_text:
                final_message = (
                    f"{final_message}\nTraceback (most recent call last):\n{tb_text}"
                )
        except Exception:
            pass

    # If explicit exception object provided: format and sanitize
    if exc is not None:
        try:
            tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
            tb_text = "".join(tb_lines)
            tb_text = _sanitize_native_stacktrace(tb_text)
            final_message = f"{final_message}\nException:\n{tb_text}"
        except Exception:
            # fallback: include sanitized str(exc)
            try:
                cleaned = _sanitize_native_stacktrace(str(exc))
                final_message = f"{final_message}\nException: {cleaned}"
            except Exception:
                final_message = f"{final_message}\nException: {repr(exc)}"

    # Emit the log
    try:
        _logger.log(level, final_message)
    except Exception:
        # Avoid raising from logger; fallback to print
        try:
            print(f"LOG FAIL [{status}]: {final_message}")
        except Exception:
            pass
