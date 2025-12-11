from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Dict, List
from urllib.parse import urljoin

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

    def _extract_all_lectures_batch(
        self, course_path: str, course_url: str
    ) -> List[Dict]:
        """Extract all lectures using JavaScript batch extraction (robust to variants)."""
        # The JS collects sections and their items. We query both possible section selectors.
        script = """
        var results = [];
        // Try both common section selectors
        var sections = document.querySelectorAll('.course-section, .slim-section');

        sections.forEach(function(section, sectionIdx) {
            // multiple possible title selectors
            var titleEl = section.querySelector('.section-title, .heading');
            var sectionTitle = titleEl ? titleEl.textContent.trim() : '';

            // find items (lecture list); different structures on different themes
            var items = section.querySelectorAll('.section-list .section-item, .bar');
            items.forEach(function(item, itemIdx) {
                // anchors for new design use 'a.item', older ones might use '.text' in .bar
                var anchor = item.querySelector('a.item') || item.querySelector('a') || item.querySelector('.text a');
                var lectureNameEl = item.querySelector('.lecture-name, .text') || item.querySelector('.title-container .lecture-name');
                var lectureTitle = lectureNameEl ? lectureNameEl.textContent.trim() : '';
                var href = anchor ? (anchor.getAttribute('href') || '') : '';
                results.push({
                    sectionIdx: sectionIdx + 1,
                    itemIdx: itemIdx + 1,
                    sectionTitle: sectionTitle,
                    title: lectureTitle,
                    url: href
                });
            });
        });
        return results;
        """

        try:
            raw_data = self.driver.execute_script(script)
        except Exception as e:
            logger.log(
                "execute_script failed during batch extraction.",
                status=logger.Status.ERROR,
                exc=e,
            )
            return self._extract_lectures_fallback(course_path)

        if not raw_data:
            logger.log(
                "No sections/lectures found by batch JS extraction, using fallback.",
                status=logger.Status.WARNING,
            )
            return self._extract_lectures_fallback(course_path)

        video_list: List[Dict] = []
        created_dirs = set()

        # regex to strip trailing duration like " (7:58)" or "( 7:58 )"
        duration_re = re.compile(r"\s*\(\s*\d{1,2}:\d{2}\s*\)\s*$")

        for item in raw_data:
            # ensure we have a sane section title
            raw_section = item.get("sectionTitle", "") or "Senza titolo sezione"
            chapter_title = clean_string(raw_section)
            if not chapter_title:
                chapter_title = "Senza titolo sezione"

            # create directory once per section
            if chapter_title not in created_dirs:
                download_path = os.path.join(course_path, chapter_title)
                try:
                    os.makedirs(download_path, exist_ok=True)
                    logger.log(
                        f"Created folder for section: {chapter_title}",
                        status=logger.Status.DEBUG,
                    )
                except Exception as e:
                    logger.log(
                        f"Failed to create directory {download_path}",
                        status=logger.Status.WARNING,
                        exc=e,
                    )
                    download_path = course_path  # fallback to course root
                created_dirs.add(chapter_title)
            else:
                download_path = os.path.join(course_path, chapter_title)

            # clean lecture title and remove duration if present
            raw_title = item.get("title", "") or ""
            raw_title = raw_title.strip()
            cleaned_title = clean_string(raw_title)
            cleaned_title = duration_re.sub(
                "", cleaned_title
            )  # remove trailing duration
            if not cleaned_title:
                cleaned_title = f"Lezione-{item.get('itemIdx', '?')}"

            truncated_title = truncate_title_to_fit_file_name(cleaned_title)

            # normalize link to absolute URL
            link = item.get("url", "") or ""
            if link and link.startswith("/"):
                try:
                    base = self.driver.current_url
                    link = urljoin(base, link)
                except Exception:
                    # best-effort fallback
                    link = link

            video_list.append(
                {
                    "link": link,
                    "title": truncated_title,
                    "idx": item.get("itemIdx", 0) or 0,
                    "download_path": download_path,
                }
            )

        logger.log(
            f"Batch extraction produced {len(video_list)} lecture entries.",
            status=logger.Status.INFO,
        )
        return video_list

    def _extract_lectures_fallback(self, course_path: str) -> List[Dict]:
        """Fallback extraction method for older layouts (kept but hardened)."""
        video_list = []
        chapter_idx = 0

        # try both slim-section and course-section
        slim_sections = self.driver.find_elements(
            By.CSS_SELECTOR, ".slim-section, .course-section"
        )
        if not slim_sections:
            logger.log(
                "Fallback: no .slim-section or .course-section elements found.",
                status=logger.Status.WARNING,
            )
            return video_list

        duration_re = re.compile(r"\s*\(\s*\d{1,2}:\d{2}\s*\)\s*$")

        for slim_section in slim_sections:
            chapter_idx += 1

            # Check if chapter is not available (drip)
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
                pass  # chapter is available

            # robustly find title
            try:
                title_el = slim_section.find_element(
                    By.CSS_SELECTOR, ".heading, .section-title"
                )
                chapter_title = clean_string(title_el.text)
            except Exception:
                chapter_title = f"Sezione-{chapter_idx}"

            download_path = os.path.join(course_path, chapter_title)
            try:
                os.makedirs(download_path, exist_ok=True)
            except Exception as e:
                logger.log(
                    f"Could not create directory {download_path}",
                    status=logger.Status.WARNING,
                    exc=e,
                )
                download_path = course_path

            # find lecture items (old/new)
            bars = slim_section.find_elements(By.CSS_SELECTOR, ".bar, .section-item")
            for idx, bar in enumerate(bars, 1):
                try:
                    # try various selectors
                    video_el = None
                    try:
                        video_el = bar.find_element(
                            By.CSS_SELECTOR, ".text a, a.item, a"
                        )
                    except Exception:
                        # find text container fallback
                        try:
                            video_el = bar.find_element(By.CSS_SELECTOR, ".text")
                        except Exception:
                            video_el = None

                    if video_el:
                        link = video_el.get_attribute("href") or ""
                        raw_title = ""
                        try:
                            # try lecture name
                            raw_title = bar.find_element(
                                By.CSS_SELECTOR, ".lecture-name"
                            ).text
                        except Exception:
                            try:
                                raw_title = video_el.text
                            except Exception:
                                raw_title = ""
                        title = clean_string(raw_title)
                        title = duration_re.sub("", title)
                        truncated_title = truncate_title_to_fit_file_name(
                            title or f"Lezione-{idx}"
                        )

                        video_list.append(
                            {
                                "link": link,
                                "title": truncated_title,
                                "idx": idx,
                                "download_path": download_path,
                            }
                        )
                except Exception as e:
                    logger.log(
                        "Error while parsing a lecture entry in fallback.",
                        status=logger.Status.DEBUG,
                        exc=e,
                    )
                    continue

        logger.log(
            f"Fallback extraction produced {len(video_list)} lecture entries.",
            status=logger.Status.INFO,
        )
        return video_list

    def get_course_title_next(self, course_url: str) -> str:
        """Get course title for simple format."""
        # Check if the driver is on the course page
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

    def download_course(self, course_url: str) -> "TeachableDownloader":
        """Download simple format course (hardened)."""
        logger.log("Detected simple course format", status=logger.Status.INFO)

        course_title = self.get_course_title_next(course_url)
        logger.log(f"Course: {course_title}", status=logger.Status.INFO)

        course_path = create_course_folder(course_title)
        self.save_course_html(course_path)

        # Download course image (best-effort)
        try:
            image_element = self.driver.find_element(
                By.XPATH, '//*[@id="__next"]/div/div/div[2]/div/div[1]/img'
            )
            image_link = image_element.get_attribute("src")
            if image_link:
                image_path = os.path.join(course_path, "course-image.jpg")
                response = requests.get(image_link, timeout=20)
                if response.ok:
                    with open(image_path, "wb") as f:
                        f.write(response.content)
                    logger.log("Image downloaded", status=logger.Status.INFO)
        except Exception as e:
            logger.log(
                "Could not find or download course image:",
                status=logger.Status.DEBUG,
                exc=e,
            )

        # Extract and download lectures
        try:
            video_list = self._extract_all_lectures_batch(course_path, course_url)
        except Exception as e:
            logger.log(
                "Error during lecture extraction.", status=logger.Status.ERROR, exc=e
            )
            video_list = []

        if not video_list:
            logger.log(
                "No videos found for the course. Exiting download gracefully.",
                status=logger.Status.WARNING,
            )
            return self.driver_wrapper

        # Defensive call to downloader - catch and log any exceptions so the whole program doesn't crash silently
        try:
            self.driver_wrapper = download_videos_from_links(
                self.driver_wrapper, video_list
            )
        except Exception as e:
            logger.log(
                "Error during download_videos_from_links",
                status=logger.Status.ERROR,
                exc=e,
            )

        return self.driver_wrapper
