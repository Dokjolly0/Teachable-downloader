import time

from selenium.webdriver.common.by import By

import src.helpers.logger as logger
from src.teachable.teachable_downloader import TeachableDownloader


def bypass_cloudflare(teachable: "TeachableDownloader") -> TeachableDownloader:
    if teachable.driver.capabilities["browserVersion"].split(".")[0] < "115":
        return teachable
    logger.log("Bypassing cloudflare", status=logger.Status.INFO)
    time.sleep(1)
    if teachable.check_elem_exists(
        By.ID, "challenge-stage", timeout=teachable.global_timeout
    ):
        try:
            teachable.driver.find_element(
                By.ID, "challenge-stage"
            ).click()  # make sure the challenge is focused
            teachable.driver.execute_script(
                '''window.open("''' + teachable.driver.current_url + """","_blank");"""
            )  # open page in new tab
            input(
                "\033[93mWarning: Bypassing Cloudflare\nplease click on the captcha checkbox if not done already "
                "and press enter to continue (do not close any of the tabs)\033[0m"
            )
            teachable.driver.switch_to.window(
                window_name=teachable.driver.window_handles[0]
            )  # switch to first tab
            teachable.driver.close()  # close first tab
            teachable.driver.switch_to.window(
                window_name=teachable.driver.window_handles[0]
            )  # switch back to new tab
        except Exception as e:
            logger.log(
                "Could not bypass cloudflare: " + str(e), status=logger.Status.ERROR
            )
            return teachable
        return teachable
    else:
        logger.log("No need to bypass cloudflare", status=logger.Status.INFO)
        return teachable
