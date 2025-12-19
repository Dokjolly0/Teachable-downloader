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
from src.helpers.exception import save_debug_artifacts
from src.helpers.file_helper import clean_string, session_cookie_file_for_email
from src.helpers.html_element import check_element_exists
from src.helpers.session import load_cookies_from_file_and_apply, save_cookies_to_file
from src.interfaces.startup_arguments import StartupArguments
from src.teachable.auth.login import find_login, login
from src.teachable.download.course_downloader_factory import CourseDownloaderFactory
from src.teachable.download.download_subtitle import download_subtitle
from src.teachable.download.download_video import download_video
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
        It will attempt to restore a saved session (cookies) for `email` before prompting for OTP.
        """
        # Attempt to restore cookies/session before performing the login flow.
        cookie_file = session_cookie_file_for_email(email)
        restored = False
        try:
            if os.path.isfile(cookie_file):
                logger.log(
                    "Found saved session cookies — attempting to restore session",
                    status=logger.Status.INFO,
                )
                try:
                    applied = load_cookies_from_file_and_apply(
                        self.driver, cookie_file, course_url
                    )
                    if applied:
                        # After applying cookies, visit the course page and check whether login is required
                        self.driver.get(course_url)
                        time.sleep(1)
                        # If the page does not show a Login link, assume we are authenticated
                        if not check_element_exists(self, By.LINK_TEXT, "Login"):
                            logger.log(
                                "Session restored successfully, login not required.",
                                status=logger.Status.INFO,
                            )
                            restored = True
                        else:
                            logger.log(
                                "Session cookies applied but login still required (session may be expired).",
                                status=logger.Status.INFO,
                            )
                    else:
                        logger.log(
                            "Could not apply saved cookies (no cookies applied).",
                            status=logger.Status.INFO,
                        )

                        logger.log("Starting login", status=logger.Status.INFO)
                        # If a login_url is provided, navigate there (we later navigate to course).
                        if login_url is None:
                            try:
                                find_login(self, course_url)
                            except Exception as e:
                                logger.log(
                                    "Could not find login:",
                                    status=logger.Status.ERROR,
                                    exc=e,
                                )
                        else:
                            self.driver.get(login_url)
                except Exception as e:
                    logger.log(
                        "Session restore attempt failed:",
                        status=logger.Status.DEBUG,
                        exc=e,
                    )
        except Exception as e:
            # Any issues should not stop the flow; we'll proceed to normal login
            logger.log(
                "Could not restore session:",
                status=logger.Status.ERROR,
                exc=e,
            )
            raise e

        # If we did not restore a valid session, perform the interactive/OTP login.
        if not restored:
            try:
                login(self, email)
            except Exception as e:
                tb = traceback.format_exc()
                logger.log(f"Could not login:\n{tb}", status=logger.Status.ERROR, exc=e)
                # save debug artifacts for debugging purposes
                try:
                    save_debug_artifacts(self.driver, prefix="login_failure")
                except Exception:
                    pass
                return
            else:
                # If login() returned without exception, try to save the cookies for later reuse.
                try:
                    saved = save_cookies_to_file(self.driver, cookie_file)
                    if saved:
                        logger.log(
                            f"Saved session cookies to {cookie_file}",
                            status=logger.Status.INFO,
                        )
                    else:
                        logger.log(
                            "Could not save session cookies (save failed).",
                            status=logger.Status.WARNING,
                        )
                except Exception as e:
                    logger.log(
                        "Failed to save session cookies:",
                        status=logger.Status.DEBUG,
                        exc=e,
                    )

        logger.log(
            "Starting download of course: " + course_url, status=logger.Status.INFO
        )
        try:
            self.pick_course_downloader(course_url)
        except Exception as e:
            logger.log(
                f"Could not download course: {course_url} cause:",
                status=logger.Status.ERROR,
                exc=e,
            )

    def start_multi_downloader(self, url_array, email, login_url):
        """
        This method handles batch downloading of courses. It navigates to the given URLs, tries to restore session
        using the same approach used by start_donwloader, and initiates the download process for each course.
        """
        logger.log("Starting login", status=logger.Status.INFO)

        if login_url is not None:
            self.driver.get(login_url)
        else:
            logger.log("Login url is not set", status=logger.Status.INFO)
            return

        # Attempt session restore for batch mode too
        cookie_file = session_cookie_file_for_email(email)
        restored = False
        try:
            if os.path.isfile(cookie_file):
                logger.log(
                    "Found saved session cookies — attempting to restore session (batch mode)",
                    status=logger.Status.INFO,
                )
                try:
                    applied = load_cookies_from_file_and_apply(
                        self.driver,
                        cookie_file,
                        url_array[0] if url_array else login_url,
                    )
                    if applied:
                        # After applying cookies, visit first course URL and check whether login is required
                        self.driver.get(url_array[0] if url_array else login_url)
                        time.sleep(1)
                        if not check_element_exists(self, By.LINK_TEXT, "Login"):
                            logger.log(
                                "Session restored successfully (batch mode), login not required.",
                                status=logger.Status.INFO,
                            )
                            restored = True
                        else:
                            logger.log(
                                "Batch mode: session cookies applied but login still required (may be expired).",
                                status=logger.Status.INFO,
                            )
                except Exception as e:
                    logger.log(
                        "Batch session restore attempt failed:",
                        status=logger.Status.DEBUG,
                        exc=e,
                    )
        except Exception:
            pass

        if not restored:
            try:
                login(self, email)
            except Exception as e:
                tb = traceback.format_exc()
                logger.log(
                    f"Could not login (batch mode):\n{tb}",
                    status=logger.Status.ERROR,
                    exc=e,
                )
                try:
                    save_debug_artifacts(self.driver, prefix="login_failure")
                except Exception:
                    pass
                return
            else:
                try:
                    saved = save_cookies_to_file(self.driver, cookie_file)
                    if saved:
                        logger.log(
                            f"Saved session cookies to {cookie_file} (batch mode)",
                            status=logger.Status.INFO,
                        )
                    else:
                        logger.log(
                            "Could not save session cookies (batch mode)",
                            status=logger.Status.WARNING,
                        )
                except Exception as e:
                    logger.log(
                        "Failed to save session cookies (batch mode):",
                        status=logger.Status.DEBUG,
                        exc=e,
                    )

        logger.log("Running batch download of courses ", status=logger.Status.INFO)
        for url in url_array:
            try:
                self.pick_course_downloader(url)
            except Exception as e:
                logger.log(
                    f"Could not download course: {url} cause:",
                    status=logger.Status.ERROR,
                    exc=e,
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

        logger.log("Picking course downloader", status=logger.Status.INFO)

        # Use factory to get appropriate downloader
        downloader = CourseDownloaderFactory.create_downloader(self)
        if downloader:
            return downloader.download_course(course_url)
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

    def _download_video_and_subs_parallel(self, link, title, video_index, output_path):
        """Download parallelo di video e sottotitoli"""
        # Implememt threading or multiprocessing here
        try:
            self = download_video(self, link, title, video_index, output_path)
        except Exception as e:
            logger.log(
                f"Video download failed: {title}", status=logger.Status.ERROR, exc=e
            )

        try:
            self = download_subtitle(self, link, title, video_index, output_path)
        except Exception as e:
            logger.log(
                f"Subtitle download failed: {title}",
                status=logger.Status.WARNING,
                exc=e,
            )

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
