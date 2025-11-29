import os
import time
import traceback
from typing import Any, cast
from urllib.parse import urlparse, urlunparse

import selenium.webdriver.support.expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from seleniumbase import Driver

import src.helpers.logger as logger
from src.helpers.check_element_exists import check_element_exists
from src.helpers.exception import save_debug_artifacts
from src.helpers.file_helper import clean_string
from src.interfaces.startup_arguments import StartupArguments
from src.teachable.auth.login import find_login, login
from src.teachable.download.download_course_classic import download_course_classic
from src.teachable.download.download_course_colossal import download_course_colossal
from src.teachable.download.download_course_simple import download_course_simple
from src.utils.cloudflare_bypass import bypass_cloudflare


class TeachableDownloader:
    def __init__(self, args: StartupArguments):
        self.driver = Driver(uc=True, headed=True)
        self.headers = {
            "User-Agent": args.user_agent,
            "Origin": "https://player.hotmart.com",
            "Referer": "https://player.hotmart.com",
        }
        self.verbose = args.verbose_level
        self._complete_lecture = args.complete_lecture
        self.global_timeout = args.selenium_driver_timeout

    def start_donwloader(self, course_url, email, login_url):
        """
        Run the downloader
        This method handles the login process and initiates the download of a single course.
        :param course_url: str
            The URL of the course to be downloaded.
        :param email: str
            The email address used to log in to the platform.
        :param login_url: str
            The URL of the login page. If not provided, manual login is assumed.
        :return: None
        """
        logger.log("Starting login", status=logger.Status.INFO)

        # Check if login_url is not set
        if login_url is None:
            try:
                find_login(self, course_url)
            except Exception as e:
                logger.log(f"Could not find login: {e}", status=logger.Status.ERROR)
        else:
            self.driver.get(login_url)

        try:
            login(self, email)
        except Exception as e:
            tb = traceback.format_exc()
            logger.log(f"Could not login: {e}\n{tb}", status=logger.Status.ERROR)
            # salva artefatti per debugging
            try:
                save_debug_artifacts(self.driver, prefix="login_failure")
            except Exception:
                pass
            return

        logger.log(
            "Starting download of course: " + course_url, status=logger.Status.INFO
        )
        try:
            self.pick_course_downloader(course_url)
        except Exception as e:
            logger.log(
                f"Could not download course: {course_url} cause: {e}",
                status=logger.Status.ERROR,
            )

    def start_multi_downloader(self, url_array, email, login_url):
        """
        This method handles batch downloading of courses. It navigates to the given URLs, logs in if necessary,
        and initiates the download process for each course.

        :param url_array: List[str]
            An array of URLs pointing to the courses that need to be downloaded.
        :param email: str
            The email address used to log in to the platform.
        :param login_url: str
            The URL of the login page. If not provided, manual login is assumed.
        :param man_login_url: str
            The URL of the page to navigate to after manual login. This parameter is optional.
            If provided, the script will wait until the user has manually navigated to this URL
            before starting the download process.
        :return: None
        """
        logger.log("Starting login", status=logger.Status.INFO)

        if login_url is not None:
            self.driver.get(login_url)
        else:
            logger.log("Login url is not set", status=logger.Status.INFO)
            return

        try:
            login(self, email)
        except Exception as e:
            tb = traceback.format_exc()
            logger.log(f"Could not login: {e}\n{tb}", status=logger.Status.ERROR)
            # salva artefatti per debugging
            try:
                save_debug_artifacts(self.driver, prefix="login_failure")
            except Exception:
                pass
            return

        logger.log("Running batch download of courses ", status=logger.Status.INFO)
        for url in url_array:
            try:
                self.pick_course_downloader(url)
            except Exception as e:
                logger.log(
                    f"Could not download course: {url} cause: {e}",
                    status=logger.Status.ERROR,
                )

    def construct_sign_in_url(self, course_url):
        parsed_url = urlparse(course_url)
        # Replace the path with '/sign_in'
        sign_in_path = "/sign_in"
        fallback_url = urlunparse(
            (parsed_url.scheme, parsed_url.netloc, sign_in_path, "", "", "")
        )
        return fallback_url

    def pick_course_downloader(self, course_url):
        # Check if we are already on the course page
        if not self.driver.current_url == course_url:
            logger.log("Switching to course page", status=logger.Status.INFO)
            self.driver.get(course_url)
            if check_element_exists(self, By.ID, "challenge-stage"):
                self = bypass_cloudflare(self)

        _ = WebDriverWait(self.driver, timeout=self.global_timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # https://support.teachable.com/hc/en-us/articles/360058715732-Course-Design-Templates
        logger.log("Picking course downloader", status=logger.Status.INFO)
        if self.driver.find_elements(By.ID, "__next"):
            logger.log("Choosing __next format", status=logger.Status.INFO)
            self = download_course_simple(self, course_url)
        elif self.driver.find_elements(By.CLASS_NAME, "course-mainbar"):
            logger.log("Choosing course-mainbar format", status=logger.Status.INFO)
            self = download_course_classic(self)
        elif self.driver.find_elements(By.CSS_SELECTOR, ".block__curriculum"):
            logger.log("Choosing .block__curriculum format", status=logger.Status.INFO)
            self = download_course_colossal(self)
        else:
            logger.log(
                "Downloader does not support this course template. Please open an issue on github.",
                status=logger.Status.ERROR,
            )

    def get_course_title_next(self, course_url):
        if self.driver.current_url != course_url:
            self.driver.get(course_url)

        WebDriverWait(self.driver, self.global_timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".wrap"))
        )
        heading = WebDriverWait(self.driver, self.global_timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".heading"))
        )
        course_title = heading.text

        course_title = clean_string(course_title)
        return course_title

    def complete_lecture(self):
        # Complete lecture
        self.driver.switch_to.default_content()
        complete_button = self.driver.find_element(By.ID, "lecture_complete_button")
        if complete_button:
            logger.log("Found complete button", status=logger.Status.INFO)
            complete_button.click()
            logger.log("Completed lecture", status=logger.Status.INFO)
            time.sleep(3)

    def save_webpage_as_html(self, title, video_index, output_path):
        output_file = os.path.join(
            output_path, "{:02d}-{}.html".format(video_index, title)
        )
        with open(output_file, "w+", encoding="utf-8") as f:
            f.write(self.driver.page_source)
        logger.log("Saved webpage as html: " + output_file, status=logger.Status.INFO)

    def save_webpage_as_pdf(self, title, video_index, output_path):
        output_file_pdf = os.path.join(
            output_path, "{:02d}-{}.pdf".format(video_index, title)
        )
        real_driver = cast(Any, getattr(self.driver, "driver", self.driver))
        real_driver.save_print_page(output_file_pdf)
        logger.log(
            "Saved webpage as pdf: " + output_file_pdf, status=logger.Status.INFO
        )

    def clean_up(self):
        logger.log("Cleaning up", status=logger.Status.INFO)
        self.driver.quit()
        # Delete cookies.txt
        if os.path.exists("cookies.txt"):
            os.remove("cookies.txt")
