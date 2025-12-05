from __future__ import annotations

import os
from typing import TYPE_CHECKING, Dict, List

import selenium.webdriver.support.expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.wait import WebDriverWait

import src.helpers.logger as logger
from src.helpers.file_helper import (
    clean_string,
    create_course_folder,
    truncate_title_to_fit_file_name,
)
from src.helpers.get_course_title import get_course_title
from src.teachable.download.course_downloader_base import BaseCourseDownloader
from src.teachable.download.download_videos_from_links import download_videos_from_links

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader


class ClassicCourseDownloader(BaseCourseDownloader):
    """Downloader for courses with 'course-mainbar' format."""

    def __init__(self, driver_wrapper: "TeachableDownloader"):
        super().__init__(driver_wrapper)

    def process_lecture_section(
        self, section_element: WebElement, chapter_idx: int, course_path: str
    ) -> List[Dict]:
        """Process a section in classic format."""
        chapter_title = section_element.find_element(
            By.CSS_SELECTOR, ".section-title"
        ).text
        chapter_title = clean_string(chapter_title)
        filename = f"{chapter_idx} {chapter_title}.mp4"
        logger.log(f"Chapter: {filename}", status=logger.Status.INFO)

        download_path = os.path.join(course_path, filename)
        os.makedirs(download_path, exist_ok=True)

        video_list = []
        idx = 1

        section_items = section_element.find_elements(By.CSS_SELECTOR, ".section-item")
        for item in section_items:
            lecture_link = item.find_element(By.CLASS_NAME, "item").get_attribute(
                "href"
            )
            lecture_title = item.find_element(By.CLASS_NAME, "lecture-name").text
            lecture_title = clean_string(lecture_title)

            truncated_title = truncate_title_to_fit_file_name(lecture_title)

            video_list.append(
                {
                    "link": lecture_link,
                    "title": truncated_title,
                    "idx": idx,
                    "download_path": download_path,
                }
            )
            idx += 1

        return video_list

    def download_course(self, course_url: str) -> "TeachableDownloader":
        """Download classic format course."""
        logger.log("Detected classic course format", status=logger.Status.INFO)

        course_title = get_course_title(self.driver, self.global_timeout)
        course_title = clean_string(course_title)
        logger.log(f"Course: {course_title}", status=logger.Status.INFO)

        course_path = create_course_folder(course_title)
        self.save_course_html(course_path)
        self.download_course_image(course_path, [".course-image"])

        # Extract all lectures
        video_list = []
        sections = WebDriverWait(self.driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".course-section"))
        )

        for idx, section in enumerate(sections, 1):
            section_videos = self.process_lecture_section(section, idx, course_path)
            video_list.extend(section_videos)

        # Download all videos
        self.driver_wrapper = download_videos_from_links(
            self.driver_wrapper, video_list
        )
        return self.driver_wrapper


def download_course_classic(self: "TeachableDownloader") -> "TeachableDownloader":
    """Adapter function for the original interface."""
    downloader = ClassicCourseDownloader(self)
    return downloader.download_course(self.driver.current_url)
