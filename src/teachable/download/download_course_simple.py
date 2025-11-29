from __future__ import annotations

import os
from typing import TYPE_CHECKING

import requests
import selenium.webdriver.support.expected_conditions as EC
from selenium.common.exceptions import TimeoutException
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


def download_course_simple(
    self: "TeachableDownloader", course_url
) -> "TeachableDownloader":
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
            logger.log(f"Failed to download image: {e}", status=logger.Status.WARNING)
    except Exception as e:
        logger.log(f"Could not find course image:  {e}", status=logger.Status.WARNING)
        pass

    chapter_idx = 0
    video_list = []
    slim_sections = self.driver.find_elements(By.CSS_SELECTOR, ".slim-section")
    for slim_section in slim_sections:
        chapter_idx += 1
        bars = slim_section.find_elements(By.CSS_SELECTOR, ".bar")
        chapter_title = slim_section.find_element(By.CSS_SELECTOR, ".heading").text
        chapter_title = clean_string(chapter_title)
        filename = f"{chapter_idx} {chapter_title}.mp4"
        logger.log("Filename: " + filename, status=logger.Status.INFO)

        try:
            WebDriverWait(slim_section, self.global_timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".drip-tag"))
            )
            logger.log(
                'Chapter "%s" not available, skipping' + filename,
                status=logger.Status.WARNING,
            )
            continue
        except TimeoutException:
            logger.log("Chapter is available", status=logger.Status.INFO)
            pass  # Element wasn't found so the chapter is available

        download_path = os.path.join(course_path, filename)
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

    self = download_videos_from_links(self, video_list)
    return self
