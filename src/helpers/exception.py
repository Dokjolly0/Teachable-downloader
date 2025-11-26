import datetime


def save_debug_artifacts(driver, prefix="debug"):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # screenshot
    try:
        driver.save_screenshot(f"{prefix}_screenshot_{ts}.png")
    except Exception:
        pass
    # page source
    try:
        with open(f"{prefix}_pagesource_{ts}.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
    except Exception:
        pass
    # browser console logs (se disponibile)
    try:
        for entry in driver.get_log("browser"):
            with open(f"{prefix}_console_{ts}.log", "a", encoding="utf-8") as f:
                f.write(str(entry) + "\n")
    except Exception:
        pass
