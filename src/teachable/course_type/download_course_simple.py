from __future__ import annotations

import os
from typing import TYPE_CHECKING, Dict, List

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
from src.teachable.download.base_course_downloader import BaseCourseDownloader
from src.teachable.download.download_videos_from_links import download_videos_from_links

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader


class SimpleCourseDownloader(BaseCourseDownloader):
    """Downloader for courses with '__next' format."""

    def __init__(self, driver_wrapper: "TeachableDownloader"):
        super().__init__(driver_wrapper)

    def get_course_title_next(self, course_url: str) -> str:
        """Get course title for simple format."""
        if self.driver.current_url != course_url:
            self.driver.get(course_url)

        WebDriverWait(self.driver, self.global_timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".wrap"))
        )
        heading = WebDriverWait(self.driver, self.global_timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".heading"))
        )
        course_title = heading.text
        return clean_string(course_title)

    def _extract_all_lectures_batch(
        self, course_path: str, course_url: str
    ) -> List[Dict]:
        """Extract all lectures using JavaScript batch extraction."""
        script = """
        var results = [];
        var sections = document.querySelectorAll('.slim-section');

        sections.forEach(function(section, sectionIdx) {
            var chapterTitle = section.querySelector('.heading')?.textContent?.trim() || '';
            var isAvailable = !section.querySelector('.drip-tag');

            if (isAvailable) {
                var bars = section.querySelectorAll('.bar');
                bars.forEach(function(bar, barIdx) {
                    var video = bar.querySelector('.text');
                    if (video) {
                        results.push({
                            sectionIdx: sectionIdx + 1,
                            barIdx: barIdx + 1,
                            chapterTitle: chapterTitle,
                            title: video.textContent?.trim() || '',
                            url: video.getAttribute('href') || ''
                        });
                    }
                });
            }
        });
        return results;
        """

        try:
            raw_data = self.driver.execute_script(script)
            video_list = []

            for item in raw_data:
                chapter_title = clean_string(item["chapterTitle"])
                filename = f"{item['sectionIdx']} {chapter_title}.mp4"
                download_path = os.path.join(course_path, filename)
                os.makedirs(download_path, exist_ok=True)

                title = clean_string(item["title"])
                truncated_title = truncate_title_to_fit_file_name(title)

                video_list.append(
                    {
                        "link": item["url"],
                        "title": truncated_title,
                        "idx": item["barIdx"],
                        "download_path": download_path,
                    }
                )

            return video_list

        except Exception as e:
            logger.log(
                "Batch extraction failed, using fallback:",
                status=logger.Status.WARNING,
                exc=e,
            )
            return self._extract_lectures_fallback(course_path)

    def _extract_lectures_fallback(self, course_path: str) -> List[Dict]:
        """Fallback extraction method."""
        video_list = []
        chapter_idx = 0

        slim_sections = self.driver.find_elements(By.CSS_SELECTOR, ".slim-section")
        for slim_section in slim_sections:
            chapter_idx += 1

            # Check if chapter is available
            try:
                WebDriverWait(slim_section, self.global_timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".drip-tag"))
                )
                logger.log(
                    f"Chapter {chapter_idx} not available, skipping",
                    status=logger.Status.WARNING,
                )
                continue
            except TimeoutException:
                pass  # Chapter is available

            chapter_title = slim_section.find_element(By.CSS_SELECTOR, ".heading").text
            chapter_title = clean_string(chapter_title)
            download_path = os.path.join(course_path, chapter_title)
            os.makedirs(download_path, exist_ok=True)

            bars = slim_section.find_elements(By.CSS_SELECTOR, ".bar")
            for idx, bar in enumerate(bars, 1):
                video = bar.find_element(By.CSS_SELECTOR, ".text")
                link = video.get_attribute("href")
                title = clean_string(video.text)
                truncated_title = truncate_title_to_fit_file_name(title)

                video_list.append(
                    {
                        "link": link,
                        "title": truncated_title,
                        "idx": idx,
                        "download_path": download_path,
                    }
                )

        return video_list

    def download_course(self, course_url: str) -> "TeachableDownloader":
        """Download simple format course."""
        logger.log("Detected simple course format", status=logger.Status.INFO)

        course_title = self.get_course_title_next(course_url)
        logger.log(f"Course: {course_title}", status=logger.Status.INFO)

        course_path = create_course_folder(course_title)
        self.save_course_html(course_path)

        # Download course image
        try:
            image_element = self.driver.find_element(
                By.XPATH, '//*[@id="__next"]/div/div/div[2]/div/div[1]/img'
            )
            image_link = image_element.get_attribute("src")
            if image_link:
                image_path = os.path.join(course_path, "course-image.jpg")
                response = requests.get(image_link)
                if response.ok:
                    with open(image_path, "wb") as f:
                        f.write(response.content)
                    logger.log("Image downloaded", status=logger.Status.INFO)
        except Exception as e:
            logger.log(
                "Could not find course image:", status=logger.Status.WARNING, exc=e
            )

        # Extract and download lectures
        video_list = self._extract_all_lectures_batch(course_path, course_url)
        self.driver_wrapper = download_videos_from_links(
            self.driver_wrapper, video_list
        )

        return self.driver_wrapper


def download_course_simple(
    self: "TeachableDownloader", course_url: str
) -> "TeachableDownloader":
    """Adapter function for the original interface."""
    downloader = SimpleCourseDownloader(self)
    return downloader.download_course(course_url)
