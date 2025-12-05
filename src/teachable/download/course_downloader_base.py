"""
Base class for all course downloaders with common functionality.
"""

from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING, Dict, List, Optional

import requests
from selenium.webdriver.common.by import By

import src.helpers.logger as logger
from src.teachable.download.download_video import download_with_yt_dlp
from src.teachable.download.download_video_file import download_video_file

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader


class BaseCourseDownloader:
    """Base class with common functionality for all course downloaders."""

    def __init__(self, driver_wrapper: "TeachableDownloader"):
        self.driver_wrapper = driver_wrapper
        self.driver = driver_wrapper.driver
        self.global_timeout = driver_wrapper.global_timeout

    def save_course_html(self, course_path: str) -> None:
        """Save the course HTML for debugging/backup."""
        try:
            output_file = os.path.join(course_path, "course.html")
            with open(output_file, "w+", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            logger.log("Saved course HTML", status=logger.Status.INFO)
        except Exception as e:
            logger.log(
                "Could not save course HTML:", status=logger.Status.WARNING, exc=e
            )

    def download_course_image(
        self, course_path: str, image_selectors: List[str]
    ) -> None:
        """Download course image using provided selectors."""
        for selector in image_selectors:
            try:
                image_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if image_elements:
                    image_element = image_elements[0]
                    image_link = image_element.get_attribute("src")
                    if not image_link:
                        continue

                    logger.log("Found course image", status=logger.Status.INFO)
                    # Try to get HD version
                    image_link_hd = re.sub(r"/resize=.+?/", "/", image_link)

                    # Try HD link first, fallback to original
                    for link in [image_link_hd, image_link]:
                        response = requests.get(link)
                        if response.ok:
                            image_path = os.path.join(course_path, "course-image.jpg")
                            with open(image_path, "wb") as f:
                                f.write(response.content)
                            logger.log(
                                "Image downloaded successfully.",
                                status=logger.Status.INFO,
                            )
                            return

                    logger.log(
                        "Failed to download image.", status=logger.Status.WARNING
                    )
                    return
            except Exception:
                continue

        logger.log("Could not find course image", status=logger.Status.DEBUG)

    def extract_video_link_from_page(self) -> Optional[str]:
        """
        Search page for video links (.m3u8 or .mp4) using multiple heuristics.
        Returns the first found link or None.
        """
        # Try __NEXT_DATA__ extraction first
        media_asset = self._extract_mediaasset_from_next_data()
        if media_asset:
            return media_asset

        # Try various element selectors
        search_methods = [
            self._find_in_anchors,
            self._find_in_video_elements,
            self._find_in_scripts,
        ]

        for method in search_methods:
            link = method()
            if link:
                return link

        return None

    def _extract_mediaasset_from_next_data(self) -> Optional[str]:
        """Extract media asset URL from __NEXT_DATA__ if present."""
        try:
            script_element = self.driver.find_element(By.ID, "__NEXT_DATA__")
            script = script_element.get_attribute("innerHTML")
            if not script:
                return None

            data = json.loads(script)

            # Try common paths
            paths_to_try = [
                ["props", "pageProps", "applicationData", "mediaAssets"],
                ["props", "pageProps", "mediaAssets"],
                ["mediaAssets"],
            ]

            for path in paths_to_try:
                result = self._get_nested_value(data, path)
                if result and isinstance(result, list) and len(result) > 0:
                    entry = result[0]
                    return entry.get("urlEncrypted") or entry.get("url")

            # Recursive search as fallback
            def _search(node):
                if isinstance(node, dict):
                    for k, v in node.items():
                        if k == "mediaAssets" and isinstance(v, list) and v:
                            entry = v[0]
                            return entry.get("urlEncrypted") or entry.get("url")
                        res = _search(v)
                        if res:
                            return res
                elif isinstance(node, list):
                    for item in node:
                        res = _search(item)
                        if res:
                            return res
                return None

            return _search(data)

        except Exception:
            return None

    def _get_nested_value(self, data, keys):
        """Safely get nested value from dictionary."""
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def _find_in_anchors(self) -> Optional[str]:
        """Search <a> tags for video links."""
        try:
            anchors = self.driver.find_elements(By.TAG_NAME, "a")
            for anchor in anchors:
                try:
                    href = anchor.get_attribute("href") or ""
                    if ".m3u8" in href or href.endswith(".mp4"):
                        return href
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _find_in_video_elements(self) -> Optional[str]:
        """Search <video> and <source> tags for video links."""
        try:
            videos = self.driver.find_elements(By.TAG_NAME, "video")
            for video in videos:
                try:
                    src = video.get_attribute("src") or ""
                    if src and (".m3u8" in src or src.endswith(".mp4")):
                        return src

                    sources = video.find_elements(By.TAG_NAME, "source")
                    for source in sources:
                        source_src = (
                            source.get_attribute("src")
                            or source.get_attribute("data-src")
                            or ""
                        )
                        if source_src and (
                            ".m3u8" in source_src or source_src.endswith(".mp4")
                        ):
                            return source_src
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _find_in_scripts(self) -> Optional[str]:
        """Search script tags for video links."""
        try:
            scripts = self.driver.find_elements(By.TAG_NAME, "script")
            for script in scripts:
                try:
                    text = script.get_attribute("innerHTML") or ""
                    if "m3u8" in text or "mediaAssets" in text:
                        patterns = [
                            r"https?://[^\s\"']+\.m3u8[^\s\"']*",
                            r"https?://[^\s\"']+\.mp4[^\s\"']*",
                        ]
                        for pattern in patterns:
                            match = re.search(pattern, text)
                            if match:
                                return match.group(0)
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def download_lecture_video(self, lecture_info: Dict, max_attempts: int = 3) -> bool:
        """
        Attempt to download a lecture video using multiple strategies.
        Returns True if successful.
        """
        title = lecture_info["title"]
        idx = lecture_info["idx"]
        download_path = lecture_info["download_path"]

        logger.log(f"Processing lecture: {title}", status=logger.Status.INFO)

        # Strategy 1: Try attachment download first
        try:
            if download_video_file(self.driver_wrapper, title, idx, download_path):
                final_mp4 = os.path.join(
                    download_path, f"{str(idx).zfill(2)}-{title}.mp4"
                )
                if os.path.isfile(final_mp4) and os.path.getsize(final_mp4) > 0:
                    logger.log(
                        f"Downloaded via attachment: {final_mp4}",
                        status=logger.Status.INFO,
                    )
                    return True
        except Exception as e:
            logger.log(
                "Attachment download attempt failed:", status=logger.Status.DEBUG, exc=e
            )

        # Strategy 2: Extract and download via yt-dlp
        attempts = 0
        while attempts < max_attempts:
            link = self.extract_video_link_from_page()
            if link:
                logger.log(
                    f"Found video link for '{title}': {link}", status=logger.Status.INFO
                )
                try:
                    success = download_with_yt_dlp(
                        self.driver_wrapper, link, title, idx, download_path
                    )
                    if success:
                        logger.log(
                            f"Download successful for: {title}",
                            status=logger.Status.INFO,
                        )
                        return True
                except Exception as e:
                    logger.log(
                        f"yt-dlp download failed for {title}:",
                        status=logger.Status.WARNING,
                        exc=e,
                    )

            attempts += 1
            if attempts < max_attempts:
                import time

                time.sleep(0.8)

        logger.log(f"Failed to download lecture: {title}", status=logger.Status.WARNING)
        return False

    def save_lecture_html(self, title: str, idx: int, download_path: str) -> None:
        """Save the lecture HTML for debugging."""
        try:
            lecture_html_name = f"{str(idx).zfill(2)}-{title}.html"
            lecture_html_path = os.path.join(download_path, lecture_html_name)
            with open(lecture_html_path, "w+", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            logger.log(
                f"Saved lecture HTML: {lecture_html_path}", status=logger.Status.INFO
            )
        except Exception as e:
            logger.log(
                "Could not save lecture HTML:", status=logger.Status.DEBUG, exc=e
            )

    def process_lecture_section(
        self, section_element, chapter_idx: int, course_path: str
    ) -> List[Dict]:
        """
        Process a section/chapter and return list of lecture info dictionaries.
        To be implemented by subclasses.

        Args:
            section_element: The web element representing the course section
            chapter_idx: Index number of the chapter/section
            course_path: Base path where course files are saved
        """
        raise NotImplementedError

    def download_course(self, course_url: str) -> "TeachableDownloader":
        """
        Main download method to be implemented by subclasses.
        """
        raise NotImplementedError
