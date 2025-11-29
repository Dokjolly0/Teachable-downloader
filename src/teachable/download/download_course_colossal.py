from __future__ import annotations

import os
import string
from typing import TYPE_CHECKING

import selenium.webdriver.support.expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

import src.helpers.logger as logger
from src.helpers.file_helper import (
    clean_string,
    create_course_folder,
    truncate_title_to_fit_file_name,
)
from src.teachable.download.download_videos_from_links import download_videos_from_links

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader


def download_course_colossal(self: "TeachableDownloader") -> TeachableDownloader:
    logger.log("Detected block course format", status=logger.Status.INFO)
    try:
        logger.log("Getting course title", status=logger.Status.INFO)
        course_title = (
            WebDriverWait(self.driver, self.global_timeout)
            .until(EC.presence_of_element_located((By.CSS_SELECTOR, ".course__title")))
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
        filename = f"{chapter_idx} {chapter_title}.mp4"
        logger.log("Filename: " + filename, status=logger.Status.INFO)

        download_path = os.path.join(course_path, filename)
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

    self = download_videos_from_links(self, video_list)
    return self
