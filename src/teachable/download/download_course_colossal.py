from __future__ import annotations

import json
import os
import re
import string
import time
from typing import TYPE_CHECKING, Optional

import selenium.webdriver.support.expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

import src.helpers.logger as logger
from src.helpers.file_helper import (
    clean_string,
    create_course_folder,
    truncate_title_to_fit_file_name,
)
from src.teachable.download.download_video import download_with_yt_dlp
from src.teachable.download.download_video_file import download_video_file

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader


def _extract_mediaasset_from_next_data(driver) -> Optional[str]:
    """Attempt to extract a media asset URL from __NEXT_DATA__ if present."""
    try:
        script = driver.find_element(By.ID, "__NEXT_DATA__").get_attribute("innerHTML")
        if not script:
            return None
        j = json.loads(script)
        # try several common paths where mediaAssets appear
        # try props.pageProps.applicationData.mediaAssets
        ma = (
            j.get("props", {})
            .get("pageProps", {})
            .get("applicationData", {})
            .get("mediaAssets")
        )
        if ma and isinstance(ma, list) and len(ma) > 0:
            cand = ma[0].get("urlEncrypted") or ma[0].get("url") or None
            if cand:
                return cand

        # fallback: search recursively for "mediaAssets" anywhere in dict (defensive)
        def _search(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k == "mediaAssets" and isinstance(v, list) and v:
                        entry = v[0]
                        return entry.get("urlEncrypted") or entry.get("url")
                    else:
                        res = _search(v)
                        if res:
                            return res
            elif isinstance(node, list):
                for itm in node:
                    res = _search(itm)
                    if res:
                        return res
            return None

        res = _search(j)
        return res
    except Exception:
        return None


def _find_link_in_page(driver) -> Optional[str]:
    """Search page for obvious video links (.m3u8 or .mp4) using multiple heuristics."""
    try:
        # 1) anchors
        anchors = driver.find_elements(By.TAG_NAME, "a")
        for a in anchors:
            try:
                href = a.get_attribute("href") or ""
                if ".m3u8" in href or href.endswith(".mp4"):
                    return href
            except Exception:
                continue
    except Exception:
        pass

    try:
        # 2) <video> and <source>
        videos = driver.find_elements(By.TAG_NAME, "video")
        for v in videos:
            try:
                src = v.get_attribute("src") or ""
                if src and (".m3u8" in src or src.endswith(".mp4")):
                    return src
                sources = v.find_elements(By.TAG_NAME, "source")
                for s in sources:
                    try:
                        ssrc = (
                            s.get_attribute("src") or s.get_attribute("data-src") or ""
                        )
                        if ssrc and (".m3u8" in ssrc or ssrc.endswith(".mp4")):
                            return ssrc
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass

    try:
        # 3) try __NEXT_DATA__
        cand = _extract_mediaasset_from_next_data(driver)
        if cand:
            return cand
    except Exception:
        pass

    try:
        # 4) search scripts for http links to m3u8/mp4 (fallback)
        scripts = driver.find_elements(By.TAG_NAME, "script")
        for s in scripts:
            try:
                text = s.get_attribute("innerHTML") or ""
                if "m3u8" in text or "mediaAssets" in text:
                    m = re.search(r"https?://[^\s\"']+\.m3u8[^\s\"']*", text)
                    if not m:
                        m = re.search(r"https?://[^\s\"']+\.mp4[^\s\"']*", text)
                    if m:
                        return m.group(0)
            except Exception:
                continue
    except Exception:
        pass

    return None


def download_course_colossal(self: "TeachableDownloader") -> "TeachableDownloader":
    """
    Download course using the 'block__curriculum' (colossal) layout.
    Strategy:
      - find sections and lectures,
      - for each lecture: click it (forces lazy load), wait a bit,
        try several extraction heuristics, then download (attachment first, then yt-dlp).
    """
    logger.log("Detected block course format", status=logger.Status.INFO)

    # try to get course title and prepare folder
    try:
        logger.log("Getting course title", status=logger.Status.INFO)
        title_el = WebDriverWait(self.driver, self.global_timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".course__title"))
        )
        course_title = title_el.text
    except Exception as e:
        logger.log(
            "Could not get course title, using tab title instead:",
            status=logger.Status.WARNING,
            exc=e,
        )
        course_title = self.driver.title

    course_title_clean = clean_string(course_title)
    course_path = create_course_folder(course_title_clean)

    # Save main course HTML with utf-8 encoding; don't abort if fails
    logger.log("Saving course html", status=logger.Status.INFO)
    try:
        output_file = os.path.join(course_path, "course.html")
        with open(output_file, "w+", encoding="utf-8") as f:
            f.write(self.driver.page_source)
    except Exception as e:
        logger.log("Could not save course html:", status=logger.Status.WARNING, exc=e)

    # Ensure curriculum sections are visible
    try:
        self.driver.execute_script(
            '[...document.querySelectorAll(".hidden")].map(e=>e.classList.remove("hidden"))'
        )
    except Exception:
        pass

    # Find sections
    try:
        sections = WebDriverWait(self.driver, self.global_timeout).until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, ".block__curriculum__section")
            )
        )
    except Exception:
        logger.log(
            "No curriculum sections found on this page.", status=logger.Status.ERROR
        )
        return self

    chapter_idx = 1
    for section in sections:
        try:
            chapter_title = section.find_element(
                By.CSS_SELECTOR, ".block__curriculum__section__title"
            ).text
            chapter_title = clean_string(chapter_title)
        except Exception:
            chapter_title = f"Chapter {chapter_idx}"
        chapter_folder_name = f"{chapter_idx} {chapter_title}.mp4"
        logger.log("Filename: " + chapter_folder_name, status=logger.Status.INFO)

        download_path = os.path.join(course_path, chapter_folder_name)
        os.makedirs(download_path, exist_ok=True)

        # Collect lecture elements within this section
        try:
            lecture_elems = section.find_elements(
                By.CSS_SELECTOR, ".block__curriculum__section__list__item__link"
            )
        except Exception:
            lecture_elems = []

        idx = 1
        for lec_elem in lecture_elems:
            # get visible title text (some links contain nested elements)
            try:
                lecture_title_el = lec_elem.find_element(
                    By.CSS_SELECTOR,
                    ".block__curriculum__section__list__item__lecture-name",
                )
                lecture_title = lecture_title_el.text.strip()
            except Exception:
                # fallback: try link text or attribute
                try:
                    lecture_title = (
                        lec_elem.text.strip()
                        or lec_elem.get_attribute("href")
                        or f"Lecture {idx}"
                    )
                except Exception:
                    lecture_title = f"Lecture {idx}"

            # sanitize and truncate for filenames
            lecture_title = clean_string(lecture_title)
            lecture_title = "".join(
                ch for ch in lecture_title if ch in string.printable
            )
            truncated = truncate_title_to_fit_file_name(lecture_title)

            logger.log(f"Found lecture: {lecture_title}", status=logger.Status.INFO)
            logger.log(f"Processing: {lecture_title}", status=logger.Status.INFO)

            # Scroll into view and click the lecture element to force load
            try:
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", lec_elem
                    )
                except Exception:
                    pass
                lec_elem.click()
                # wait a short moment for the frontend to populate media data
                time.sleep(0.6)
            except Exception as e:
                logger.log(
                    "Could not click lecture element:",
                    status=logger.Status.DEBUG,
                    exc=e,
                )
                # even if click fails, continue to try extraction in current page state

            # After click, allow a little more time and try again (some pages need slightly longer)
            attempts = 0
            found_link = None
            while attempts < 3 and not found_link:
                # 1) try attachment download (this function will set chrome download dir etc. and click attachment)
                try:
                    # download_video_file returns True if it succeeded (or skipped if exists)
                    ok = download_video_file(self, truncated, idx, download_path)
                    if ok:
                        # check presence of final file
                        final_mp4 = os.path.join(
                            download_path, f"{str(idx).zfill(2)}-{truncated}.mp4"
                        )
                        if os.path.isfile(final_mp4) and os.path.getsize(final_mp4) > 0:
                            logger.log(
                                f"Downloaded via attachment: {final_mp4}",
                                status=logger.Status.INFO,
                            )
                            found_link = "attachment"  # mark as success
                            break
                except Exception as e:
                    logger.log(
                        "Attachment download attempt raised:",
                        status=logger.Status.DEBUG,
                        exc=e,
                    )

                # 2) try to find direct link in page
                try:
                    found_link = _find_link_in_page(self.driver)
                    if found_link:
                        break
                except Exception:
                    pass

                # 3) if not found, wait a bit and retry (allow dynamic JS to populate)
                attempts += 1
                time.sleep(0.8)

            if found_link == "attachment":
                # already downloaded by attachment method
                idx += 1
                continue

            if not found_link:
                logger.log(
                    f"No video link found for lecture: {lecture_title}",
                    status=logger.Status.DEBUG,
                )
                idx += 1
                continue

            # We have a link (m3u8 or mp4). Attempt yt-dlp download.
            logger.log(
                f"Attempting yt-dlp download for lecture '{lecture_title}' using link: {found_link}",
                status=logger.Status.INFO,
            )
            try:
                success = download_with_yt_dlp(
                    self, found_link, truncated, idx, download_path
                )
            except Exception as e:
                logger.log(
                    "yt-dlp helper raised exception:",
                    status=logger.Status.WARNING,
                    exc=e,
                )
                success = False

            if success:
                logger.log(
                    f"download_with_yt_dlp succeeded for lecture: {lecture_title}",
                    status=logger.Status.INFO,
                )
            else:
                logger.log(
                    f"download_with_yt_dlp failed for lecture: {lecture_title}",
                    status=logger.Status.WARNING,
                )

            # Save the lecture HTML for debugging / record
            try:
                # Build a file name for the lecture html
                lecture_html_name = f"{str(idx).zfill(2)}-{truncated}.html"
                lecture_html_path = os.path.join(download_path, lecture_html_name)
                with open(lecture_html_path, "w+", encoding="utf-8") as fh:
                    fh.write(self.driver.page_source)
                logger.log(
                    f"Saved webpage as html: {lecture_html_path}",
                    status=logger.Status.INFO,
                )
            except Exception as e:
                logger.log(
                    "Could not save lecture HTML:", status=logger.Status.DEBUG, exc=e
                )

            idx += 1

        chapter_idx += 1

    return self
