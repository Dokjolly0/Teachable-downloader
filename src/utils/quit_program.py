import sys
from typing import NoReturn


def quit_program(status: int = 0) -> NoReturn:
    print("Uscita dal programma")
    sys.exit(status)
