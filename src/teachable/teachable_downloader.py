from __future__ import annotations

import json
import os
import re
import string
import time
import traceback
from typing import Any, cast
from urllib.parse import urlparse, urlunparse

import requests
import selenium.webdriver.support.expected_conditions as EC
from selenium.common import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from seleniumbase import Driver

import src.helpers.logger as logger
from src.helpers.check_element_exists import check_element_exists
from src.helpers.exception import save_debug_artifacts
from src.helpers.file_helper import (
    clean_string,
    create_course_folder,
    truncate_title_to_fit_file_name,
)
from src.interfaces.startup_arguments import StartupArguments
from src.teachable.auth.login import find_login, login
from src.teachable.download.downlaod_video_attachments import download_attachments
from src.teachable.download.download_subtitle import download_subtitle
from src.teachable.download.download_video import download_video
from src.teachable.download.download_video_file import download_video_file
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

    def run(self, course_url, email, login_url):
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

    def run_batch(self, url_array, email, login_url):
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
                self = download_attachments(
                    self,
                    video["link"],
                    video["title"],
                    video["idx"],
                    video["download_path"],
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
                if download_video_file(
                    self, video["title"], video["idx"], video["download_path"]
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
                        self = download_subtitle(
                            self,
                            link,
                            video_title,
                            video["idx"],
                            video["download_path"],
                        )
                    except Exception as e:
                        logger.log(
                            f"Could not download subtitle: {video_title} cause: {e}",
                            status=logger.Status.WARNING,
                        )

                    try:
                        logger.log("Downloading video", status=logger.Status.INFO)
                        self = download_video(
                            self,
                            link,
                            video_title,
                            video["idx"],
                            video["download_path"],
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
