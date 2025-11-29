from __future__ import annotations

import glob
import json
import os
import re
from typing import TYPE_CHECKING

import selenium.webdriver.support.expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

import src.helpers.logger as logger
from src.teachable.download.download_video import download_with_yt_dlp
from src.teachable.download.download_video_file import download_video_file

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader


def _cleanup_leftovers_for_target(target_dir: str, expected_basename: str) -> None:
    try:
        patterns = [
            f"{expected_basename}.*.crdownload",
            f"{expected_basename}.crdownload",
            f"{expected_basename}.part",
            f"{expected_basename}.part-*",
            f"{expected_basename}.*.part",
            f"{expected_basename}.*.part-*",
        ]
        for pat in patterns:
            for p in glob.glob(os.path.join(target_dir, pat)):
                try:
                    os.remove(p)
                    logger.log(
                        f"Removed leftover temp file: {p}", status=logger.Status.DEBUG
                    )
                except Exception as e:
                    logger.log(
                        f"Could not remove temp file {p}:",
                        status=logger.Status.DEBUG,
                        exc=e,
                    )
    except Exception as e:
        logger.log("Leftover cleanup error:", status=logger.Status.DEBUG, exc=e)


def _make_video_id(video: dict) -> str:
    download_path = video.get("download_path", "")
    idx = video.get("idx")
    title = video.get("title", "")
    return f"{os.path.normpath(download_path)}|{idx}|{title}"


def download_videos_from_links(
    self: "TeachableDownloader", video_list
) -> "TeachableDownloader":
    original_window = self.driver.current_window_handle

    if video_list and len(video_list) > 0:
        first_download_path = video_list[0].get("download_path", "")
        course_root = (
            os.path.dirname(first_download_path) if first_download_path else "."
        )
    else:
        course_root = "."

    state_file = os.path.join(course_root, ".download_state.json")
    try:
        if os.path.isfile(state_file):
            with open(state_file, "r", encoding="utf-8") as f:
                course_state = json.load(f)
        else:
            course_state = {"completed": []}
    except Exception:
        course_state = {"completed": []}

    completed = set(course_state.get("completed", []))

    for video in video_list:
        vid_id = _make_video_id(video)
        expected_basename = "{:02d}-{}".format(
            int(video.get("idx", 0)), str(video.get("title", "")).strip()
        )
        download_path = video.get("download_path", ".")

        if vid_id in completed:
            logger.log(
                f"Skipping already completed lecture (state): {video['title']}",
                status=logger.Status.INFO,
            )
            continue

        final_mp4 = os.path.join(download_path, f"{expected_basename}.mp4")
        if os.path.isfile(final_mp4) and os.path.getsize(final_mp4) > 0:
            logger.log(
                f"Skipping already downloaded file: {final_mp4}",
                status=logger.Status.INFO,
            )
            completed.add(vid_id)
            try:
                with open(state_file, "w", encoding="utf-8") as f:
                    json.dump(
                        {"completed": list(completed)}, f, ensure_ascii=False, indent=2
                    )
            except Exception:
                pass
            continue

        try:
            logger.log(f"Processing: {video['title']}", status=logger.Status.INFO)
            _cleanup_leftovers_for_target(download_path, expected_basename)

            # Open lecture in new tab
            self.driver.execute_script(f"window.open('{video['link']}', '_blank');")
            new_handles = [
                h for h in self.driver.window_handles if h != original_window
            ]
            if not new_handles:
                logger.log(
                    f"Could not open new tab for lecture: {video['title']}",
                    status=logger.Status.WARNING,
                )
                continue
            new_window = new_handles[-1]
            self.driver.switch_to.window(new_window)
            WebDriverWait(self.driver, 8).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Save page HTML (already handled elsewhere) then try to find video links by multiple strategies
            # Strategy cascade: attachments -> anchors with m3u8/mp4 -> video/source tags -> iframe -> __NEXT_DATA__
            found_link = None

            # 1) Try direct attachment element (existing approach)
            try:
                if download_video_file(
                    self, video["title"], video["idx"], video["download_path"]
                ):
                    # If this succeeded we consider it done (file will be on disk)
                    if os.path.isfile(final_mp4) and os.path.getsize(final_mp4) > 0:
                        logger.log(
                            f"Marking lecture as completed (attachment): {video['title']}",
                            status=logger.Status.INFO,
                        )
                        completed.add(vid_id)
                        with open(state_file, "w", encoding="utf-8") as f:
                            json.dump(
                                {"completed": list(completed)},
                                f,
                                ensure_ascii=False,
                                indent=2,
                            )
                        # close tab and continue
                        self.driver.close()
                        self.driver.switch_to.window(original_window)
                        continue
            except Exception as e:
                logger.log(
                    "Attachment method errored:", status=logger.Status.DEBUG, exc=e
                )

            # 2) Look for anchor tags with m3u8 or .mp4
            try:
                anchors = self.driver.find_elements(By.TAG_NAME, "a")
                for a in anchors:
                    try:
                        href = a.get_attribute("href") or ""
                        if ".m3u8" in href or href.endswith(".mp4"):
                            found_link = href
                            logger.log(
                                f"Found direct anchor link: {href}",
                                status=logger.Status.DEBUG,
                            )
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            # 3) Look for <video> and <source> tags
            if not found_link:
                try:
                    videos = self.driver.find_elements(By.TAG_NAME, "video")
                    for v in videos:
                        try:
                            src = v.get_attribute("src")
                            if src and (".m3u8" in src or src.endswith(".mp4")):
                                found_link = src
                                logger.log(
                                    f"Found video[src]: {src}",
                                    status=logger.Status.DEBUG,
                                )
                                break
                            # try source children
                            sources = v.find_elements(By.TAG_NAME, "source")
                            for s in sources:
                                ssrc = (
                                    s.get_attribute("src")
                                    or s.get_attribute("data-src")
                                    or ""
                                )
                                if ssrc and (".m3u8" in ssrc or ssrc.endswith(".mp4")):
                                    found_link = ssrc
                                    logger.log(
                                        f"Found source[src]: {ssrc}",
                                        status=logger.Status.DEBUG,
                                    )
                                    break
                            if found_link:
                                break
                        except Exception:
                            continue
                except Exception:
                    pass

            # 4) Look into iframes (inspect src or __NEXT_DATA__ inside)
            if not found_link:
                try:
                    iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    for i, iframe in enumerate(iframes):
                        try:
                            src = iframe.get_attribute("src") or ""
                            if src and (".m3u8" in src or src.endswith(".mp4")):
                                found_link = src
                                logger.log(
                                    f"Found iframe src with direct link: {src}",
                                    status=logger.Status.DEBUG,
                                )
                                break
                            # switch into iframe and look for __NEXT_DATA__ or sources
                            self.driver.switch_to.frame(iframe)
                            # try __NEXT_DATA__
                            try:
                                script = self.driver.find_element(
                                    By.ID, "__NEXT_DATA__"
                                )
                                if script:
                                    text = script.get_attribute("innerHTML") or ""
                                    try:
                                        import json as _json

                                        parsed = _json.loads(text)
                                        # try common path to media assets
                                        ma = parsed.get("props", {}).get(
                                            "pageProps", {}
                                        ).get("applicationData", {}).get(
                                            "mediaAssets"
                                        ) or parsed.get("props", {}).get(
                                            "pageProps", {}
                                        ).get("video", {}).get("mediaAssets")
                                        if ma and isinstance(ma, list) and len(ma) > 0:
                                            candidate = (
                                                ma[0].get("urlEncrypted")
                                                or ma[0].get("url")
                                                or ""
                                            )
                                            if candidate:
                                                found_link = candidate
                                                logger.log(
                                                    "Found mediaAsset url in __NEXT_DATA__",
                                                    status=logger.Status.DEBUG,
                                                )
                                                # leave iframe
                                                self.driver.switch_to.default_content()
                                                break
                                    except Exception:
                                        pass
                            except Exception:
                                pass

                            # search sources inside iframe
                            try:
                                vids = self.driver.find_elements(By.TAG_NAME, "video")
                                for vv in vids:
                                    try:
                                        vsrc = vv.get_attribute("src") or ""
                                        if vsrc and (
                                            ".m3u8" in vsrc or vsrc.endswith(".mp4")
                                        ):
                                            found_link = vsrc
                                            break
                                        s_srcs = vv.find_elements(By.TAG_NAME, "source")
                                        for ss in s_srcs:
                                            ssrc = ss.get_attribute("src") or ""
                                            if ssrc and (
                                                ".m3u8" in ssrc or ssrc.endswith(".mp4")
                                            ):
                                                found_link = ssrc
                                                break
                                        if found_link:
                                            break
                                    except Exception:
                                        continue
                                if found_link:
                                    self.driver.switch_to.default_content()
                                    break
                            except Exception:
                                pass
                        except Exception:
                            # ensure we switch back anyway
                            try:
                                self.driver.switch_to.default_content()
                            except Exception:
                                pass
                            continue
                    # ensure default_content
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass
                except Exception:
                    pass

            # 5) Try to parse JSON inside scripts in the main document (fallback)
            if not found_link:
                try:
                    scripts = self.driver.find_elements(By.TAG_NAME, "script")
                    for s in scripts:
                        try:
                            text = s.get_attribute("innerHTML") or ""
                            if "mediaAssets" in text or "m3u8" in text:
                                # try to find an http link
                                m = re.search(
                                    r"https?://[^\s\"']+\.m3u8[^\s\"']*", text
                                )
                                if not m:
                                    m = re.search(
                                        r"https?://[^\s\"']+\.mp4[^\s\"']*", text
                                    )
                                if m:
                                    found_link = m.group(0)
                                    logger.log(
                                        f"Found link in script tag: {found_link}",
                                        status=logger.Status.DEBUG,
                                    )
                                    break
                        except Exception:
                            continue
                except Exception:
                    pass

            # If we found a link, attempt download via yt-dlp
            download_ok = False
            if found_link:
                logger.log(
                    f"Attempting yt-dlp download for lecture '{video['title']}' using link: {found_link}",
                    status=logger.Status.INFO,
                )
                try:
                    download_ok = download_with_yt_dlp(
                        self,
                        found_link,
                        video["title"],
                        video["idx"],
                        video["download_path"],
                    )
                except Exception as e:
                    logger.log(
                        "yt-dlp helper raised exception:",
                        status=logger.Status.WARNING,
                        exc=e,
                    )
                    download_ok = False

                if download_ok:
                    logger.log(
                        f"Marking lecture as completed (yt-dlp): {video['title']}",
                        status=logger.Status.INFO,
                    )
                    completed.add(vid_id)
                    try:
                        with open(state_file, "w", encoding="utf-8") as f:
                            json.dump(
                                {"completed": list(completed)},
                                f,
                                ensure_ascii=False,
                                indent=2,
                            )
                    except Exception:
                        pass
                else:
                    logger.log(
                        f"yt-dlp could not download lecture: {video['title']}",
                        status=logger.Status.WARNING,
                    )
            else:
                logger.log(
                    f"No video link found for lecture: {video['title']}",
                    status=logger.Status.DEBUG,
                )

        except Exception as e:
            logger.log(
                f"Failed processing lecture '{video.get('title', '')}':",
                status=logger.Status.ERROR,
                exc=e,
            )
        finally:
            # Close tab if still open and return to original
            try:
                if len(self.driver.window_handles) > 1:
                    self.driver.close()
                if original_window in self.driver.window_handles:
                    self.driver.switch_to.window(original_window)
                else:
                    # fallback to first handle
                    self.driver.switch_to.window(self.driver.window_handles[0])
            except Exception:
                pass

    return self
