from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import src.helpers.logger as logger
from src.helpers.check_element_exists import check_element_exists
from src.teachable.auth.handle_otp_login import handle_otp_login
from src.utils.cloudflare_bypass import bypass_cloudflare


def find_login(self: "TeachableDownloader", course_url):
    logger.log("Trying to find login", status=logger.Status.INFO)
    self.driver.implicitly_wait(self.global_timeout)
    self.driver.get(course_url)

    try:
        login_element = WebDriverWait(self.driver, self.global_timeout).until(
            EC.presence_of_element_located((By.LINK_TEXT, "Login"))
        )
    except TimeoutException:
        logger.log(
            "Login button not found, navigating to fallback URL",
            status=logger.Status.WARNING,
        )
        fallback_url = self.construct_sign_in_url(course_url)
        self.driver.get(fallback_url)
    else:
        login_element.click()


def login(self, email):
    logger.log("Logging in", status=logger.Status.INFO)
    # Cloudflare bypass
    if check_element_exists(self, By.ID, "challenge-stage"):
        self = bypass_cloudflare(self)

    # Wait for the login form to appear
    _ = WebDriverWait(self.driver, timeout=15).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    email_element = WebDriverWait(self.driver, self.global_timeout).until(
        EC.presence_of_element_located((By.ID, "email"))
    )
    access_button = WebDriverWait(self.driver, self.global_timeout).until(
        EC.presence_of_element_located((By.ID, "otp-login-btn"))
    )
    logger.log("Filling in login form", status=logger.Status.DEBUG)
    email_element.click()
    email_element.clear()
    email_element.send_keys(email)
    access_button.click()

    # Wait for the OTP form
    logger.log("Waiting for OTP code", status=logger.Status.DEBUG)
    self = handle_otp_login(self)
    logger.log("Logged in, switching to course page", status=logger.Status.INFO)
    time.sleep(3)
