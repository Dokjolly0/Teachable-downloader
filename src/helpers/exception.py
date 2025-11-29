import datetime
import os

import src.helpers.logger as logger


def save_debug_artifacts(driver, prefix="debug"):
    logs_path = os.path.join(os.getcwd(), "logs")
    screenshot_path = os.path.join(logs_path, "screenshots")
    page_source_path = os.path.join(logs_path, "page_source")
    console_logs_path = os.path.join(logs_path, "console_logs")

    # Create directories
    os.makedirs(screenshot_path, exist_ok=True)
    os.makedirs(page_source_path, exist_ok=True)
    os.makedirs(console_logs_path, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # --- Screenshot ---
    try:
        screenshot_filename = f"{prefix}_screenshot_{ts}.png"
        full_screenshot_path = os.path.join(screenshot_path, screenshot_filename)
        driver.save_screenshot(full_screenshot_path)
    except Exception as e:
        logger.log("Error saving screenshot:", logger.Status.ERROR, exc=e)
        pass

    # --- Page Source ---
    try:
        pagesource_filename = f"{prefix}_pagesource_{ts}.html"
        full_pagesource_path = os.path.join(page_source_path, pagesource_filename)
        with open(full_pagesource_path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
    except Exception as e:
        logger.log("Error saving page source:", logger.Status.ERROR, exc=e)
        pass

    # --- Browser Console Logs ---
    try:
        console_filename = f"{prefix}_console_{ts}.log"
        full_console_path = os.path.join(console_logs_path, console_filename)
        with open(full_console_path, "a", encoding="utf-8") as f:
            for entry in driver.get_log("browser"):
                f.write(str(entry) + "\n")
    except Exception as e:
        logger.log("Error saving console logs:", logger.Status.ERROR, exc=e)
        pass
