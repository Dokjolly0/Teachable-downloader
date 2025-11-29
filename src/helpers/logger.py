import logging
import traceback
from enum import Enum
from typing import Optional

from src.interfaces.startup_arguments import StartupArguments
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


def log(
    message: str,
    status: Status = Status.INFO,
    verbose_level: int = -1,
    exc: Optional[Exception] = None,
    exc_info: bool = False,
):
    """
    Improved logging with traceback support.

    - exc: pass an Exception object to print its traceback.
    - exc_info=True: prints the current exception traceback (inside except).
    """

    # Determine effective verbosity
    if verbose_level in {0, 1, 2}:
        log_level = [logging.WARNING, logging.INFO, logging.DEBUG][verbose_level]
    else:
        log_level = _get_default_verbose_level()

    _ensure_logger_configured(log_level)

    # Map status → level
    if status == Status.ERROR:
        level = logging.ERROR
    elif status == Status.WARNING:
        level = logging.WARNING
    elif status == Status.DEBUG:
        level = logging.DEBUG
    else:
        level = logging.INFO

    final_message = message

    # Append traceback from explicit exception
    if exc is not None:
        try:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            final_message += "\n" + tb
        except Exception:
            final_message += f"\nException: {repr(exc)}"

    # Append traceback from current context
    elif exc_info:
        tb = traceback.format_exc()
        final_message += "\n" + tb

    # Emit log
    _logger.log(level, final_message)
