import logging
from enum import Enum

from src.interfaces.startup_arguments import StartupArguments
from src.utils.startup_arguments import get_startup_arguments


class Status(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"


def log(message: str, status: Status = Status.INFO, verbose_level: int = -1):
    """Function to log a message with the appropriate log level.

    Args:
        verbose_level (int): The verbosity level of the log message.
        status (Status): The status of the log message.
    Returns:
        None
    """
    log_level = logging.WARNING

    if verbose_level == 0:
        log_level = logging.WARNING
    elif verbose_level == 1:
        log_level = logging.INFO
    elif verbose_level == 2:
        log_level = logging.DEBUG
    else:
        args: StartupArguments = get_startup_arguments()
        log_level = args.verbose_level

    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    if status == Status.ERROR:
        logging.error(message)
    elif status == Status.WARNING:
        logging.warning(message)
    elif status == Status.INFO:
        logging.info(message)
    elif status == Status.DEBUG:
        logging.debug(message)
