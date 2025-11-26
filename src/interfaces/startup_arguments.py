from dataclasses import dataclass


@dataclass
class StartupArguments:
    """Startup arguments for the application."""

    url: str
    email: str
    password: str
    verbose: bool
    complete_lecture: bool
    login_url: str
    manual_login_url: str
    file_urls_path: str
    user_agent: str
    selenium_driver_timeout: int
