from __future__ import annotations

import os
import string
import time
from typing import TYPE_CHECKING, Dict, List, Optional

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

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader


class ColossalCourseDownloader(BaseCourseDownloader):
    """Downloader for courses with 'block__curriculum' format."""

    def __init__(self, driver_wrapper: "TeachableDownloader"):
        super().__init__(driver_wrapper)

    def process_lecture_section(
        self, section_element: WebElement, chapter_idx: int, course_path: str
    ) -> List[Dict]:
        """Process a section in colossal format."""
        try:
            chapter_title = section_element.find_element(
                By.CSS_SELECTOR, ".block__curriculum__section__title"
            ).text
            chapter_title = clean_string(chapter_title)
        except Exception:
            chapter_title = f"Chapter {chapter_idx}"

        chapter_folder_name = f"{chapter_idx} {chapter_title}.mp4"
        logger.log(f"Chapter: {chapter_folder_name}", status=logger.Status.INFO)

        download_path = os.path.join(course_path, chapter_folder_name)
        os.makedirs(download_path, exist_ok=True)

        video_list = []

        # Process lectures
        try:
            lecture_elems = section_element.find_elements(
                By.CSS_SELECTOR, ".block__curriculum__section__list__item__link"
            )
        except Exception:
            lecture_elems = []

        for idx, lec_elem in enumerate(lecture_elems, 1):
            lecture_info = self._extract_lecture_info(lec_elem, idx)
            if lecture_info:
                lecture_info["download_path"] = download_path
                video_list.append(lecture_info)

        return video_list

    def _extract_lecture_info(
        self, lecture_element: WebElement, idx: int
    ) -> Optional[Dict]:
        """Extract lecture information from element."""
        try:
            title_el = lecture_element.find_element(
                By.CSS_SELECTOR,
                ".block__curriculum__section__list__item__lecture-name",
            )
            lecture_title = title_el.text.strip()
        except Exception:
            try:
                lecture_title = (
                    lecture_element.text.strip()
                    or lecture_element.get_attribute("href")
                    or f"Lecture {idx}"
                )
            except Exception:
                lecture_title = f"Lecture {idx}"

        lecture_title = clean_string(lecture_title)
        lecture_title = "".join(ch for ch in lecture_title if ch in string.printable)
        truncated = truncate_title_to_fit_file_name(lecture_title)

        return {
            "link": lecture_element.get_attribute("href"),
            "title": truncated,
            "idx": idx,
            "element": lecture_element,
        }

    def _process_lecture_element(self, lecture_info: Dict) -> bool:
        """Process a single lecture element by clicking and downloading."""
        element = lecture_info.get("element")
        if element:
            try:
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", element
                )
                element.click()
                time.sleep(0.6)
            except Exception as e:
                logger.log(
                    "Could not click lecture:", status=logger.Status.DEBUG, exc=e
                )

        return self.download_lecture_video(lecture_info)

    def download_course(self, course_url: str) -> "TeachableDownloader":
        """Download colossal format course."""
        logger.log("Detected colossal course format", status=logger.Status.INFO)

        # Try to reveal hidden elements
        try:
            self.driver.execute_script(
                '[...document.querySelectorAll(".hidden")].map(e=>e.classList.remove("hidden"))'
            )
        except Exception:
            pass

        course_title = get_course_title(self.driver, self.global_timeout)
        course_title = clean_string(course_title)
        course_path = create_course_folder(course_title)

        self.save_course_html(course_path)

        # Find sections
        try:
            sections = WebDriverWait(self.driver, self.global_timeout).until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, ".block__curriculum__section")
                )
            )
        except Exception:
            logger.log("No curriculum sections found", status=logger.Status.ERROR)
            return self.driver_wrapper

        # Process each section
        for chapter_idx, section in enumerate(sections, 1):
            video_list = self.process_lecture_section(section, chapter_idx, course_path)

            # Download each lecture in this section
            for lecture_info in video_list:
                success = self._process_lecture_element(lecture_info)
                if success:
                    self.save_lecture_html(
                        lecture_info["title"],
                        lecture_info["idx"],
                        lecture_info["download_path"],
                    )

        return self.driver_wrapper


def download_course_colossal(self: "TeachableDownloader") -> "TeachableDownloader":
    """Adapter function for the original interface."""
    downloader = ColossalCourseDownloader(self)
    return downloader.download_course(self.driver.current_url)
