from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def check_element_exists(self: TeachableDownloader, by: str, selector: str):
    """
    Check if element exists
    1. by: By.ID, By.CLASS_NAME, By.XPATH, etc.
    2. selector: the selector to find the element
    3. timeout: time to wait for the element
    4. return: True if element exists, False otherwise
    """
    try:
        WebDriverWait(self.driver, timeout=self.global_timeout).until(
            EC.presence_of_element_located((by, selector))
        )
    except NoSuchElementException:
        return False
    except TimeoutException:
        return False
    except Exception:
        return False
    else:
        return True  # If try not raise exception
