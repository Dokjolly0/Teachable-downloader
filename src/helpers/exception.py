import datetime
import os


def save_debug_artifacts(driver, prefix="debug"):
    logs_path = os.path.join(os.getcwd(), "logs")
    screenshot_path = os.path.join(logs_path, "screenshots")
    page_source_path = os.path.join(logs_path, "page_source")
    console_logs_path = os.path.join(logs_path, "console_logs")

    os.makedirs(screenshot_path, exist_ok=True)
    os.makedirs(page_source_path, exist_ok=True)
    os.makedirs(console_logs_path, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # screenshot
    try:
        driver.save_screenshot(f"screenshots/{prefix}_screenshot_{ts}.png")
    except Exception:
        pass
    # page source
    try:
        with open(
            f"page_source/{prefix}_pagesource_{ts}.html", "w", encoding="utf-8"
        ) as f:
            f.write(driver.page_source)
    except Exception:
        pass
    # browser console logs
    try:
        for entry in driver.get_log("browser"):
            with open(
                f"console_logs/{prefix}_console_{ts}.log", "a", encoding="utf-8"
            ) as f:
                f.write(str(entry) + "\n")
    except Exception:
        pass
