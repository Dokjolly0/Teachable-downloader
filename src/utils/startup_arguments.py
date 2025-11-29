import argparse
from typing import Optional

import src.helpers.logger as logger
from src.interfaces.startup_arguments import StartupArguments
from src.utils.quit_program import quit_program

startup_arguments: Optional["StartupArguments"] = None


def check_required_args(args: StartupArguments):
    if args.email:
        return True
    else:
        logger.log(
            "Email are required",
            status=logger.Status.ERROR,
            verbose_level=0,
        )
        return False


def get_cached_startup_arguments():
    return startup_arguments


def set_startup_arguments(args):
    try:
        global startup_arguments
        if startup_arguments is None:
            startup_arguments = StartupArguments(
                url=args.url,
                email=args.email,
                password=args.password,
                verbose_level=args.verbose_level,
                complete_lecture=args.complete_lecture,
                login_url=args.login_url,
                file_urls_path=args.file_urls_path,
                user_agent=args.user_agent,
                selenium_driver_timeout=args.selenium_driver_timeout,
            )
        return startup_arguments
    except KeyboardInterrupt:
        quit_program()
    except Exception as e:
        logger.log(
            "❌ Errore durante l'impostazione degli argomenti di avvio:",
            status=logger.Status.ERROR,
            exc=e,
        )
        return None


def get_startup_arguments() -> StartupArguments:
    try:
        parser = argparse.ArgumentParser(
            prog="Teachable-Dl",
            description="Download courses",
        )
        parser.add_argument("--url", required=False, help="URL of the course")
        parser.add_argument(
            "-e", "--email", required=False, help="Email of the account"
        )
        parser.add_argument(
            "-p", "--password", required=False, help="Password of the account"
        )
        parser.add_argument(
            "-v",
            "--verbose-level",
            action="count",
            default=1,
            help="Increase verbosity level (repeat for more verbosity)",
        )
        parser.add_argument(
            "--complete-lecture",
            action="store_true",
            default=False,
            help="Complete the lecture after downloading",
        )
        parser.add_argument(
            "--login-url",
            required=False,
            help="(Optional) URL to teachable SSO login page",
        )
        parser.add_argument(
            "-f",
            "--file-urls-path",
            required=False,
            help="Path to a text file that contains URLs",
        )
        parser.add_argument(
            "--user-agent",
            required=False,
            help="User agent to use when downloading videos",
            default="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/116.0.0.0 Safari/537.36",
        )
        parser.add_argument(
            "-t",
            "--selenium-driver-timeout",
            required=False,
            help="Timeout for selenium driver",
            default=10,
        )
        args = parser.parse_args()

        startup_arguments = get_cached_startup_arguments()
        if startup_arguments is None:
            startup_arguments = set_startup_arguments(args)

        if startup_arguments is not None:
            if not check_required_args(startup_arguments):
                quit_program()
            else:
                return startup_arguments
        else:
            logger.log("Startup arguments not found", status=logger.Status.ERROR)
            quit_program()

    except Exception as e:
        logger.log(
            "Error occurred while parsing startup arguments:",
            status=logger.Status.ERROR,
            exc=e,
        )
        quit_program()
