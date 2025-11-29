from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

import requests
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


def download_course_classic(self: "TeachableDownloader") -> TeachableDownloader:
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
        'Found course title: "' + course_title + '" starting cleaning of title string',
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
                logger.log("Image downloaded successfully.", status=logger.Status.INFO)
            else:
                # print a message indicating that the image download failed
                logger.log("Failed to download image.", status=logger.Status.WARNING)
    except Exception as e:
        logger.log(f"Could not find course image: {e}", status=logger.Status.WARNING)
        pass

    chapter_idx = 1
    video_list = []
    sections = WebDriverWait(self.driver, 10).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".course-section"))
    )
    for section in sections:
        chapter_title = section.find_element(By.CSS_SELECTOR, ".section-title").text
        chapter_title = clean_string(chapter_title)
        chapter_title = chapter_title = "{:02d}-{}".format(chapter_idx, chapter_title)
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

    self = download_videos_from_links(self, video_list)
    return self
