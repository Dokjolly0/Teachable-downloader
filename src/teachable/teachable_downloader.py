from __future__ import annotations

import json
import os
import re
import string
import sys
import time
from typing import Any, Dict, Optional, cast
from urllib.parse import urljoin, urlparse, urlunparse

import requests
import selenium.webdriver.support.expected_conditions as EC
import wget
import yt_dlp
from selenium.common import TimeoutException
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from seleniumbase import Driver
from yt_dlp.extractor.common import _InfoDict

import src.helpers.logger as logger
from src.helpers.ffmpeg import check_ffmpeg_available, install_ffmpeg
from src.helpers.file_helper import (
    clean_string,
    create_course_folder,
    truncate_title_to_fit_file_name,
)
from src.interfaces.startup_arguments import StartupArguments
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

    def check_elem_exists(self, by, selector, timeout):
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

    def run(self, course_url, email, password, login_url, manual_login_url):
        """
        Run the downloader
        1. course_url: URL of the course
        2. email: email of the user
        3. password: password of the user
        4. login_url: URL of the login
        5. manual_login_url: URL for manual login
        6. return: None
        """
        logger.log("Starting login", status=logger.Status.INFO)

        if manual_login_url is None:
            # Check if login_url is not set
            if login_url is None:
                try:
                    self.find_login(course_url)
                except Exception as e:
                    logger.log(f"Could not find login: {e}", status=logger.Status.ERROR)
            else:
                self.driver.get(login_url)

            try:
                self.login(email, password)
            except Exception as e:
                logger.log(f"Could not login: {e}", status=logger.Status.ERROR)
                return
        else:
            self.driver.get(course_url)
            while self.driver.current_url != manual_login_url:
                time.sleep(3)
                logger.log(
                    "Waiting for user to navigate to url: " + manual_login_url,
                    status=logger.Status.INFO,
                )
                logger.log(
                    "Current url: " + self.driver.current_url, status=logger.Status.INFO
                )

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

    def run_batch(self, url_array, email, password, login_url, man_login_url):
        """
        This method handles batch downloading of courses. It navigates to the given URLs, logs in if necessary,
        and initiates the download process for each course.

        :param url_array: List[str]
            An array of URLs pointing to the courses that need to be downloaded.
        :param email: str
            The email address used to log in to the platform.
        :param password: str
            The password associated with the provided email address.
        :param login_url: str
            The URL of the login page. If not provided, manual login is assumed.
        :param man_login_url: str
            The URL of the page to navigate to after manual login. This parameter is optional.
            If provided, the script will wait until the user has manually navigated to this URL
            before starting the download process.
        :return: None
        """
        logger.log("Starting login", status=logger.Status.INFO)

        if man_login_url is None:
            # Check if login_url is not set
            if login_url is not None:
                self.driver.get(login_url)
            else:
                logger.log("Login url is not set", status=logger.Status.INFO)
                return

            try:
                self.login(email, password)
            except Exception as e:
                logger.log(f"Could not login: {e}", status=logger.Status.ERROR)
                return
        else:
            self.driver.get(url_array[0])
            while self.driver.current_url != man_login_url:
                time.sleep(3)
                logger.log(
                    "Waiting for user to navigate to url: " + man_login_url,
                    status=logger.Status.INFO,
                )
                logger.log(
                    "Current url: " + self.driver.current_url, status=logger.Status.INFO
                )

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

    def find_login(self, course_url):
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

    def login(self, email, password):
        logger.log("Logging in", status=logger.Status.INFO)

        if self.check_elem_exists(
            By.ID, "challenge-stage", timeout=self.global_timeout
        ):
            self = bypass_cloudflare(self)

        WebDriverWait(self.driver, timeout=15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        email_element = WebDriverWait(self.driver, self.global_timeout).until(
            EC.presence_of_element_located((By.ID, "email"))
        )
        password_element = WebDriverWait(self.driver, self.global_timeout).until(
            EC.presence_of_element_located((By.ID, "password"))
        )
        commit_element = WebDriverWait(self.driver, self.global_timeout).until(
            EC.presence_of_element_located((By.NAME, "commit"))
        )

        logger.log("Filling in login form", status=logger.Status.DEBUG)
        email_element.click()
        email_element.clear()
        self.driver.execute_script(
            "document.getElementById('email').value='" + email + "'"
        )

        password_element.click()
        password_element.clear()
        self.driver.execute_script(
            "document.getElementById('password').value='" + password + "'"
        )

        commit_element.click()

        # Check for login error due to incorrect credentials
        logger.log("Checking for login error", status=logger.Status.DEBUG)
        try:
            error_elements = WebDriverWait(self.driver, self.global_timeout).until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "div.toast, span.text-with-icon")
                )
            )
            for element in error_elements:
                if "Your email or password is incorrect" in element.text:
                    logger.log(
                        "Login failed: Incorrect email or password.",
                        status=logger.Status.ERROR,
                    )
                    return False
        except TimeoutException:
            # No error message found, continue
            pass

        # Check for new device challenge
        # input with name otp_code
        if self.check_elem_exists(By.NAME, "otp_code", timeout=self.global_timeout):
            # wait for user to enter code
            input(
                "\033[93mWarning: New device challenge\nplease enter the code sent to your email and press enter to "
                "continue\033[0m"
            )
        logger.log("Logged in, switching to course page", status=logger.Status.INFO)
        time.sleep(3)

    def pick_course_downloader(self, course_url):
        # Check if we are already on the course page
        if not self.driver.current_url == course_url:
            logger.log("Switching to course page", status=logger.Status.INFO)
            self.driver.get(course_url)
            if self.check_elem_exists(
                By.ID, "challenge-stage", timeout=self.global_timeout
            ):
                self = bypass_cloudflare(self)

        WebDriverWait(self.driver, timeout=self.global_timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # https://support.teachable.com/hc/en-us/articles/360058715732-Course-Design-Templates
        logger.log("Picking course downloader", status=logger.Status.INFO)
        if self.driver.find_elements(By.ID, "__next"):
            logger.log("Choosing __next format", status=logger.Status.INFO)
            self.download_course_simple(course_url)
        elif self.driver.find_elements(By.CLASS_NAME, "course-mainbar"):
            logger.log("Choosing course-mainbar format", status=logger.Status.INFO)
            self.download_course_classic(course_url)
        elif self.driver.find_elements(By.CSS_SELECTOR, ".block__curriculum"):
            logger.log("Choosing .block__curriculum format", status=logger.Status.INFO)
            self.download_course_colossal(course_url)
        else:
            logger.log(
                "Downloader does not support this course template. Please open an issue on github.",
                status=logger.Status.ERROR,
            )

    def download_course_colossal(self, course_url):
        logger.log("Detected block course format", status=logger.Status.INFO)
        try:
            logger.log("Getting course title", status=logger.Status.INFO)
            course_title = (
                WebDriverWait(self.driver, self.global_timeout)
                .until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".course__title"))
                )
                .text
            )
        except Exception as e:
            logger.log(
                f"Could not get course title, using tab title instead: {e}",
                status=logger.Status.WARNING,
            )
            course_title = self.driver.title

        course_title = clean_string(course_title)
        course_path = create_course_folder(course_title)

        logger.log("Saving course html", status=logger.Status.INFO)
        try:
            output_file = os.path.join(course_path, "course.html")
            with open(output_file, "w+") as f:
                f.write(self.driver.page_source)
        except Exception as e:
            logger.log(f"Could not save course html: {e}", status=logger.Status.ERROR)

        # Unhide all elements
        logger.log("Unhiding all elements", status=logger.Status.INFO)
        self.driver.execute_script(
            '[...document.querySelectorAll(".hidden")].map(e=>e.classList.remove("hidden"))'
        )

        chapter_idx = 1
        video_list = []
        sections = WebDriverWait(self.driver, self.global_timeout).until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, ".block__curriculum__section")
            )
        )

        for section in sections:
            chapter_title = section.find_element(
                By.CSS_SELECTOR, ".block__curriculum__section__title"
            ).text
            chapter_title = clean_string(chapter_title)
            chapter_title = "{:02d}-{}".format(chapter_idx, chapter_title)
            logger.log("Found chapter: " + chapter_title, status=logger.Status.INFO)

            download_path = os.path.join(course_path, chapter_title)
            os.makedirs(download_path, exist_ok=True)

            chapter_idx += 1
            idx = 1

            section_items = section.find_elements(
                By.CSS_SELECTOR, ".block__curriculum__section__list__item__link"
            )
            for section_item in section_items:
                lecture_link = section_item.get_attribute("href")

                lecture_title = section_item.find_element(
                    By.CSS_SELECTOR,
                    ".block__curriculum__section__list__item__lecture-name",
                ).text
                lecture_title = clean_string(lecture_title)
                lecture_title = "".join(
                    char for char in lecture_title if char in string.printable
                )
                logger.log("Found lecture: " + lecture_title, status=logger.Status.INFO)

                truncated_lecture_title = truncate_title_to_fit_file_name(lecture_title)

                video_entity = {
                    "link": lecture_link,
                    "title": truncated_lecture_title,
                    "idx": idx,
                    "download_path": download_path,
                }
                video_list.append(video_entity)
                idx += 1

        self.download_videos_from_links(video_list)

    def download_course_classic(self, course_url):
        # self.driver.find_elements(By.CLASS_NAME, "course-mainbar")
        logger.log("Detected _mainbar course format", status=logger.Status.INFO)
        try:
            logger.log("Getting course title", status=logger.Status.DEBUG)
            course_title = (
                WebDriverWait(self.driver, self.global_timeout)
                .until(
                    EC.presence_of_element_located(
                        (
                            By.CSS_SELECTOR,
                            "body > section > div.course-sidebar > div > h2",
                        )
                    )
                )
                .text
            )
        except Exception as e:
            logger.log(
                f"Could not get course title, using tab title instead: {e}",
                status=logger.Status.WARNING,
            )
            course_title = self.driver.title

        logger.log(
            'Found course title: "'
            + course_title
            + '" starting cleaning of title string',
            status=logger.Status.DEBUG,
        )
        course_title = clean_string(course_title)
        logger.log("Found course title: " + course_title, status=logger.Status.INFO)
        course_path = create_course_folder(course_title)

        try:
            logger.log("Saving course html", status=logger.Status.INFO)
            output_file = os.path.join(course_path, "course.html")
            with open(output_file, "w+", encoding="utf-8") as f:
                f.write(self.driver.page_source)
        except Exception as e:
            logger.log(f"Could not save course html: {e}", status=logger.Status.ERROR)

        # Get course image
        try:
            image_element = self.driver.find_elements(By.CLASS_NAME, "course-image")
            logger.log("Found course image", status=logger.Status.INFO)
            image_link = image_element[0].get_attribute("src")
            image_link_hd = re.sub(r"/resize=.+?/", "/", image_link)
            # try to download the image using the modified link first
            response = requests.get(image_link_hd)
            if response.ok:
                # save the image to disk
                image_path = os.path.join(course_path, "course-image.jpg")
                with open(image_path, "wb") as f:
                    f.write(response.content)
                logger.log("Image downloaded successfully.", status=logger.Status.INFO)
            else:
                # try to download the image using the original link
                response = requests.get(image_link)
                if response.ok:
                    # save the image to disk
                    image_path = os.path.join(course_path, "course-image.jpg")
                    with open(image_path, "wb") as f:
                        f.write(response.content)
                    logger.log(
                        "Image downloaded successfully.", status=logger.Status.INFO
                    )
                else:
                    # print a message indicating that the image download failed
                    logger.log(
                        "Failed to download image.", status=logger.Status.WARNING
                    )
        except Exception as e:
            logger.log(
                f"Could not find course image: {e}", status=logger.Status.WARNING
            )
            pass

        chapter_idx = 1
        video_list = []
        sections = WebDriverWait(self.driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".course-section"))
        )
        for section in sections:
            chapter_title = section.find_element(By.CSS_SELECTOR, ".section-title").text
            chapter_title = clean_string(chapter_title)
            chapter_title = chapter_title = "{:02d}-{}".format(
                chapter_idx, chapter_title
            )
            logger.log("Found chapter: " + chapter_title, status=logger.Status.INFO)

            download_path = os.path.join(course_path, chapter_title)
            os.makedirs(download_path, exist_ok=True)

            chapter_idx += 1
            idx = 1

            section_items = section.find_elements(By.CSS_SELECTOR, ".section-item")
            for section_item in section_items:
                lecture_link = section_item.find_element(
                    By.CLASS_NAME, "item"
                ).get_attribute("href")

                lecture_title = section_item.find_element(
                    By.CLASS_NAME, "lecture-name"
                ).text
                lecture_title = clean_string(lecture_title)
                logger.log("Found lecture: " + lecture_title, status=logger.Status.INFO)

                truncated_lecture_title = truncate_title_to_fit_file_name(lecture_title)

                video_entity = {
                    "link": lecture_link,
                    "title": truncated_lecture_title,
                    "idx": idx,
                    "download_path": download_path,
                }
                video_list.append(video_entity)
                idx += 1

        self.download_videos_from_links(video_list)

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

    def download_course_simple(self, course_url):
        self.driver.implicitly_wait(2)
        logger.log("Detected next course format", status=logger.Status.INFO)
        course_title = self.get_course_title_next(course_url)
        logger.log("Found course title: " + course_title, status=logger.Status.INFO)
        course_path = create_course_folder(course_title)

        output_file = os.path.join(course_path, "course.html")
        try:
            with open(output_file, "w+", encoding="utf-8") as f:
                f.write(self.driver.page_source)
        except Exception as e:
            logger.log(f"Could not save course html: {e}", status=logger.Status.ERROR)

        # Download course image
        try:
            logger.log("Downloading course image", status=logger.Status.INFO)
            image_element = self.driver.find_element(
                By.XPATH, '//*[@id="__next"]/div/div/div[2]/div/div[1]/img'
            )
            logger.log("Found course image", status=logger.Status.INFO)
            image_link = image_element.get_attribute("src")
            # Save image
            image_path = os.path.join(course_path, "course-image.jpg")
            # send a GET request to the image link
            try:
                response = requests.get(image_link)
                # write the image data to a file
                with open(image_path, "wb") as f:
                    f.write(response.content)
                # print a message indicating that the image was downloaded
                logger.log("Image downloaded successfully.", status=logger.Status.INFO)
            except Exception as e:
                # print a message indicating that the image download failed
                logger.log(
                    f"Failed to download image: {e}", status=logger.Status.WARNING
                )
        except Exception as e:
            logger.log(
                f"Could not find course image:  {e}", status=logger.Status.WARNING
            )
            pass

        chapter_idx = 0
        video_list = []
        slim_sections = self.driver.find_elements(By.CSS_SELECTOR, ".slim-section")
        for slim_section in slim_sections:
            chapter_idx += 1
            bars = slim_section.find_elements(By.CSS_SELECTOR, ".bar")
            chapter_title = slim_section.find_element(By.CSS_SELECTOR, ".heading").text
            chapter_title = clean_string(chapter_title)
            chapter_title = "{:02d}-{}".format(chapter_idx, chapter_title)
            logger.log("Found chapter: " + chapter_title, status=logger.Status.INFO)

            try:
                WebDriverWait(slim_section, self.global_timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".drip-tag"))
                )
                logger.log(
                    'Chapter "%s" not available, skipping' + chapter_title,
                    status=logger.Status.WARNING,
                )
                continue
            except TimeoutException:
                logger.log("Chapter is available", status=logger.Status.INFO)
                pass  # Element wasn't found so the chapter is available

            download_path = os.path.join(course_path, chapter_title)
            os.makedirs(download_path, exist_ok=True)

            idx = 1
            for bar in bars:
                video = bar.find_element(By.CSS_SELECTOR, ".text")
                link = video.get_attribute("href")
                # Remove new line characters from the title and replace spaces with -
                title = clean_string(video.text)
                logger.log("Found lecture: " + title, status=logger.Status.INFO)
                truncated_title = truncate_title_to_fit_file_name(title)
                video_entity = {
                    "link": link,
                    "title": truncated_title,
                    "idx": idx,
                    "download_path": download_path,
                }
                video_list.append(video_entity)
                idx += 1

        self.download_videos_from_links(video_list)

    def download_videos_from_links(self, video_list):
        for video in video_list:
            if self.driver.current_url != video["link"]:
                logger.log(
                    "Navigating to lecture: " + video["title"],
                    status=logger.Status.INFO,
                )
                self.driver.get(video["link"])
                self.driver.implicitly_wait(self.global_timeout)
            logger.log(
                "Downloading lecture: " + video["title"], status=logger.Status.INFO
            )

            # logger.log("Disabling autoplay", status=logger.Status.INFO)
            # self.driver.execute_script('var checkbox = document.getElementById("custom-toggle-autoplay");'
            #                            'if (checkbox.checked) {checkbox.click();}')

            try:
                logger.log("Saving html", status=logger.Status.INFO)
                self.save_webpage_as_html(
                    video["title"], video["idx"], video["download_path"]
                )
            except Exception as e:
                logger.log(
                    f"Could not save html: {video['title']} cause: {e}",
                    status=logger.Status.WARNING,
                )

            try:
                logger.log("Downloading attachments", status=logger.Status.INFO)
                self.download_attachments(
                    video["link"], video["title"], video["idx"], video["download_path"]
                )
            except Exception as e:
                logger.log(
                    f"Could not download attachments: {video['title']} cause: {e}",
                    status=logger.Status.WARNING,
                )

            try:
                logger.log(
                    "Trying to download video as an attachment",
                    status=logger.Status.DEBUG,
                )
                if self.download_video_file(
                    video["title"], video["idx"], video["download_path"]
                ):
                    continue

            except Exception as e:
                logger.log(
                    f"Could not download video as an attachment: {video['title']} cause: {e}",
                    status=logger.Status.WARNING,
                )

            video_iframes = self.driver.find_elements(
                By.XPATH, "//iframe[starts-with(@data-testid, 'embed-player')]"
            )

            for i, iframe in enumerate(video_iframes):
                try:
                    logger.log("Switching to video frame", status=logger.Status.INFO)
                    self.driver.switch_to.frame(iframe)

                    script_text = self.driver.find_element(By.ID, "__NEXT_DATA__")
                    json_text = json.loads(script_text.get_attribute("innerHTML"))
                    link = json_text["props"]["pageProps"]["applicationData"][
                        "mediaAssets"
                    ][0]["urlEncrypted"]

                    # Append -n to the video title if there are multiple iframes
                    video_title = video["title"] + (
                        "-" + str(i + 1) if len(video_iframes) > 1 else ""
                    )

                    try:
                        logger.log("Downloading subtitle", status=logger.Status.INFO)
                        self.download_subtitle(
                            link, video_title, video["idx"], video["download_path"]
                        )
                    except Exception as e:
                        logger.log(
                            f"Could not download subtitle: {video_title} cause: {e}",
                            status=logger.Status.WARNING,
                        )

                    try:
                        logger.log("Downloading video", status=logger.Status.INFO)
                        self.download_video(
                            link, video_title, video["idx"], video["download_path"]
                        )
                    except Exception as e:
                        logger.log(
                            f"Could not download video: {video_title} cause: {e}",
                            status=logger.Status.WARNING,
                        )

                    self.driver.switch_to.default_content()  # Switch back to main content before the next iteration

                except Exception as e:
                    logger.log(
                        f"Could not find video: {video['title']} cause: {e}",
                        status=logger.Status.WARNING,
                    )
                    continue

            logger.log("Downloaded video: " + video["title"], status=logger.Status.INFO)

            if self._complete_lecture:
                try:
                    logger.log("Completing lecture", status=logger.Status.INFO)
                    self.complete_lecture()
                except Exception as e:
                    logger.log(
                        f"Could not complete lecture: {video['title']} cause: {e}",
                        status=logger.Status.WARNING,
                    )

        return

    def complete_lecture(self):
        # Complete lecture
        self.driver.switch_to.default_content()
        complete_button = self.driver.find_element(By.ID, "lecture_complete_button")
        if complete_button:
            logger.log("Found complete button", status=logger.Status.INFO)
            complete_button.click()
            logger.log("Completed lecture", status=logger.Status.INFO)
            time.sleep(3)

    def download_video(self, link, title, video_index, output_path):
        # Check if ffmpeg is available
        ffmpeg_path = check_ffmpeg_available()
        if not ffmpeg_path:
            install_ffmpeg()

        ydl_opts: yt_dlp._Params = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "postprocessors": [
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                },
                {
                    "key": "FFmpegMetadata",
                },
            ],
            "http_headers": self.headers,
            "concurrent_fragment_downloads": 15,
            "outtmpl": os.path.join(
                output_path, "{:02d}-{}.mp4".format(int(video_index), str(title))
            ),
            "verbose": True if self.verbose > 0 else False,
        }

        # If ffmpeg is in a specific path, add it to the options
        if ffmpeg_path != "ffmpeg":
            ydl_opts["ffmpeg_location"] = ffmpeg_path

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
        except Exception as e:
            logger.log(f"Could not download video: {title} cause: {e}")

    # This function is needed because yt-dlp subtitle downloader is not working
    def download_subtitle(self, link, title, video_index, output_path):
        # Check if ffmpeg is available
        ffmpeg_path = check_ffmpeg_available()
        if not ffmpeg_path:
            logger.log("❌ FFmpeg not found!", status=logger.Status.ERROR)
            logger.log(
                "Install ffmpeg or put it in ./bin/ffmpeg.exe",
                status=logger.Status.ERROR,
            )
            logger.log(
                "Download from: https://www.gyan.dev/ffmpeg/builds/",
                status=logger.Status.ERROR,
            )
            sys.exit(1)

        ydl_opts: yt_dlp._Params = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "postprocessors": [
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                },
                {
                    "key": "FFmpegMetadata",
                },
            ],
            "http_headers": self.headers,
            "allsubtitles": True,
            "subtitleslangs": ["all"],
            "concurrent_fragment_downloads": 10,
            "writesubtitles": True,
            "outtmpl": os.path.join(str(output_path), str(title)),
            "verbose": True if self.verbose > 0 else False,
        }

        # Se ffmpeg è in una path specifica, aggiungila alle opzioni
        if ffmpeg_path != "ffmpeg":
            ydl_opts["ffmpeg_location"] = ffmpeg_path

        info_json: Optional[_InfoDict] = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, download=False)
                info_json = ydl.sanitize_info(info)
        except Exception as e:
            logger.log(f"Could not download subtitle: {title} cause: {e}")

        subtitle_links = {}
        if (
            info_json
            and isinstance(info_json, dict)
            and "requested_subtitles" in info_json
        ):
            requested = cast(Dict[str, Any], info_json["requested_subtitles"])
            for lang, sub_info in requested.items():
                subtitle_links[lang] = {"url": sub_info["url"], "ext": sub_info["ext"]}

        # Print the subtitle links and language names
        req = None
        for lang, sub in subtitle_links.items():
            subtitle_filename = "{:02d}-{}.{}.{}".format(
                video_index, title, lang, sub["ext"]
            )
            file_path = os.path.join(output_path, subtitle_filename)
            if os.path.isfile(file_path):
                logger.log(
                    "Skipping existing subtitle: " + subtitle_filename,
                    status=logger.Status.INFO,
                )
            else:
                base_url = sub["url"]
                try:
                    req = requests.get(sub["url"], headers=self.headers)
                except Exception as e:
                    logger.log(
                        f"Could not download subtitle: {title} cause: {e}",
                        status=logger.Status.WARNING,
                    )
                relative_path = (
                    req.text.split("\n")[5]
                    if isinstance(req, requests.Response)
                    else ""
                )
                full_url = urljoin(base_url, relative_path)
                try:
                    response = requests.get(full_url, headers=self.headers)
                    with open(file_path, "wb") as f:
                        f.write(response.content)
                except Exception as e:
                    logger.log(
                        f"Could not download subtitle: {title} cause: {e}",
                        status=logger.Status.WARNING,
                    )
                logger.log(
                    "Downloaded subtitle: " + subtitle_filename,
                    status=logger.Status.INFO,
                )

    def download_video_file(self, title, video_index, output_path, timeout=-1):
        video_title = "{:02d}-{}".format(video_index, title)

        # Grab the video attachments type video
        video_attachment = self.driver.find_element(
            By.CLASS_NAME, "lecture-attachment-type-video"
        )

        if not video_attachment:
            logger.log(
                f"No video attachment found for lecture: {title}",
                status=logger.Status.DEBUG,
            )
            return False

        video_link = video_attachment.find_element(By.TAG_NAME, "a")

        if not video_link:
            logger.log(
                f"No video link found for lecture: {title}", status=logger.Status.DEBUG
            )
            return False

        # Set the download directory for this file
        self.driver.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": output_path},
        )
        # Get list of files before download
        files_before_download = set(os.listdir(output_path))

        # Click the link to trigger download
        video_link.click()

        # Wait for download to complete
        start_time = time.time()
        while True:
            files_after_download = set(os.listdir(output_path))

            # Find new files
            new_files = files_after_download - files_before_download

            if len(new_files) == 1 and not list(new_files)[0].endswith(".crdownload"):
                break

            if timeout > 0 and (time.time() - start_time) > timeout:
                logger.log(
                    f"Download timeout for lecture: {title}",
                    status=logger.Status.WARNING,
                )
                return False

            time.sleep(1)

        latest_file = os.path.join(output_path, list(new_files)[0])

        # Determine the file extension
        _, extension = os.path.splitext(latest_file)

        # Create the new filename
        new_filename = f"{video_title}{extension}"
        new_filepath = os.path.join(output_path, new_filename)

        # Rename the file
        os.rename(latest_file, new_filepath)
        logger.log(f"Downloaded video file {new_filename}", status=logger.Status.INFO)
        return True

    def download_attachments(self, link, title, video_index, output_path):
        video_title = "{:02d}-{}".format(video_index, title)

        # Grab the video attachments type file
        video_attachments = self.driver.find_elements(
            By.CLASS_NAME, "lecture-attachment-type-file"
        )
        # Get all links from the video attachments

        if video_attachments:
            video_links = video_attachments[0].find_elements(By.TAG_NAME, "a")

            output_path = os.path.join(output_path, video_title)
            os.makedirs(output_path, exist_ok=True)

            # Get href attribute from the first link
            if video_links:
                for video_link in video_links:
                    link = video_link.get_attribute("href")
                    file_name = video_link.text
                    logger.log(
                        "Downloading attachment: " + file_name + " for video: " + title,
                        status=logger.Status.INFO,
                    )
                    # Download file and save the file in output_path directory
                    wget.download(link, out=output_path)
        else:
            logger.log(
                "No attachments found for video: " + title, status=logger.Status.WARNING
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
