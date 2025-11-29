from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import src.helpers.logger as logger


def get_course_title(driver, timeout):
    logger.log("Getting course title", status=logger.Status.INFO)

    possible_selectors = [
        ".course__title",  # common Teachable theme
        ".course-sidebar h2",  # often used for course titles
        ".course-header h1",  # some use h1 instead
        "h1.course-title",  # alternate variation
        "h1",  # generic h1 as last resort
    ]

    for selector in possible_selectors:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            title = el.text.strip()
            if title:
                return title
        except Exception:
            continue

    # Final fallback
    logger.log(
        "Could not get course title via selectors, using tab title instead",
        status=logger.Status.WARNING,
    )
    return driver.title
