from dataclasses import dataclass, field


@dataclass
class StartupArguments:
    """Startup arguments for the application."""

    url: str = field(default="")
    email: str = field(default="")
    password: str = field(default="")
    verbose_level: int = field(default=0)
    complete_lecture: bool = field(default=False)
    login_url: str = field(default="")
    manual_login_url: str = field(default="")
    file_urls_path: str = field(default="")
    user_agent: str = field(default="")
    selenium_driver_timeout: int = field(default=0)
    chrome_profile_path: str = field(default="")
