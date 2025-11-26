from seleniumbase import Driver

from src.interfaces.startup_arguments import StartupArguments


class TeachableDownloader:
    def __init__(self, args: StartupArguments):
        self.driver = Driver(uc=True, headed=True)
        self.headers = {
            "User-Agent": args.user_agent,
            "Origin": "https://player.hotmart.com",
            "Referer": "https://player.hotmart.com",
        }
        self.verbose = args.verbose_level
        self._complete_lecture = args.complete_lecture
        self.global_timeout = args.selenium_driver_timeout
