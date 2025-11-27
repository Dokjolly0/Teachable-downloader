from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import selenium.webdriver.support.expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

import src.helpers.logger as logger

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader


def input_code(self: "TeachableDownloader") -> TeachableDownloader:
    code = input("Insert OTP code: ")
    codes_str = [str(c) for c in code]
    opt_code_div = WebDriverWait(self.driver, self.global_timeout).until(
        EC.presence_of_element_located((By.ID, "otp-code"))
    )
    input_elements = opt_code_div.find_elements(By.XPATH, ".//input[@type='text']")
    if len(input_elements) == len(codes_str):
        for i in range(len(codes_str)):
            digit = codes_str[i]
            input_element = input_elements[i]
            # Pulisci il campo e poi invia la cifra corrispondente
            input_element.clear()
            input_element.send_keys(digit)
            logger.log(
                f"Inserted '{digit}' in field {i + 1}",
                status=logger.Status.DEBUG,
            )
    else:
        logger.log(
            f"Error: Find {len(input_elements)} fields, but the code has {len(codes_str)} digits.",
            status=logger.Status.ERROR,
        )
    return self


def handle_otp_login(self):
    """Controls the input of the OTP, the click on Verify and the retry in case of invalid code."""

    # Consts
    VERIFY_BUTTON = (By.XPATH, '//button[./span[text()="Verify"]]')
    INVALID_CODE_CHECK = (By.XPATH, '//div[contains(., "Invalid code")]')
    MAX_ATTEMPTS = 2

    for attempt in range(1, MAX_ATTEMPTS + 1):
        logger.log(
            f"Attempting OTP input (Attempt {attempt}/{MAX_ATTEMPTS})",
            status=logger.Status.DEBUG,
        )

        # 1. Input code
        self = input_code(self)

        try:
            verify_button = WebDriverWait(self.driver, self.global_timeout).until(
                EC.presence_of_element_located(VERIFY_BUTTON)
            )
            verify_button.click()
            logger.log("Clicked 'Verify' button.", status=logger.Status.DEBUG)
        except TimeoutException:
            # If the button doesn't appear, it's a critical error in the interface
            logger.log(
                "Verify button not found within timeout.",
                status=logger.Status.ERROR,
            )
            return False

        # 3. Check for invalid code error
        try:
            WebDriverWait(self.driver, self.global_timeout).until(
                EC.presence_of_element_located(INVALID_CODE_CHECK)
            )

            if attempt < MAX_ATTEMPTS:
                logger.log(
                    "Invalid code detected. Retrying...", status=logger.Status.WARNING
                )
                continue
            else:
                logger.log(
                    "Failed to enter valid OTP code after all attempts.",
                    status=logger.Status.ERROR,
                )
                sys.exit(0)

        except TimeoutException:
            logger.log(
                "OTP code accepted or error element did not appear.",
                status=logger.Status.INFO,
            )
            return True

    return False
