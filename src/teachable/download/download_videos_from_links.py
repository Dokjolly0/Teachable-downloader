from __future__ import annotations

import glob
import json
import os
from typing import TYPE_CHECKING

import selenium.webdriver.support.expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

import src.helpers.logger as logger
from src.teachable.download.download_video_file import download_video_file

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader


# Helper: manage per-course state file to persist completed lectures across runs/crashes
def _load_course_state(course_root: str) -> dict:
    """Load or create a .download_state.json file in the course root.
    The file contains a dict with a 'completed' list of unique ids representing finished lectures.
    """
    state_file = os.path.join(course_root, ".download_state.json")
    if os.path.isfile(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.log(
                f"Could not read state file {state_file}: {e}",
                status=logger.Status.WARNING,
            )
            return {"completed": []}
    else:
        return {"completed": []}


def _save_course_state(course_root: str, state: dict) -> None:
    """Persist the state file atomically."""
    state_file = os.path.join(course_root, ".download_state.json")
    tmp = state_file + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, state_file)
    except Exception as e:
        logger.log(
            f"Could not save state file {state_file}: {e}", status=logger.Status.WARNING
        )


def _cleanup_leftovers_for_target(target_dir: str, expected_basename: str) -> None:
    """Remove common temporary download leftovers that may block resume.
    This function deletes files like {expected_basename}.crdownload, *.part, *.part-* etc.
    """
    try:
        # Look for temp patterns in target directory
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
                        f"Could not remove temp file {p}: {e}",
                        status=logger.Status.WARNING,
                    )
    except Exception as e:
        logger.log(f"Leftover cleanup error: {e}", status=logger.Status.DEBUG)


def _make_video_id(video: dict) -> str:
    """Create a stable ID for a video entry to store in state file.
    Use download_path relative to course root plus idx and sanitized title.
    """
    # download_path is typically course_root/<chapter folder>
    download_path = video.get("download_path", "")
    idx = video.get("idx")
    title = video.get("title", "")
    # Use OS-safe separators
    return f"{os.path.normpath(download_path)}|{idx}|{title}"


def download_videos_from_links(
    self: "TeachableDownloader", video_list
) -> "TeachableDownloader":
    """Version optimized for faster downloads with resume support.

    This function:
    - Maintains a per-course state file (.download_state.json) to mark completed lectures.
    - Skips videos that already exist as final files.
    - Cleans leftover temporary files before attempting a download.
    """
    original_window = self.driver.current_window_handle

    # Derive course root from first video's download_path (safe fallback if empty)
    if video_list and len(video_list) > 0:
        first_download_path = video_list[0].get("download_path", "")
        course_root = (
            os.path.dirname(first_download_path) if first_download_path else "."
        )
    else:
        course_root = "."

    course_state = _load_course_state(course_root)
    completed = set(course_state.get("completed", []))

    for video in video_list:
        vid_id = _make_video_id(video)
        expected_basename = "{:02d}-{}".format(
            int(video.get("idx", 0)), str(video.get("title", "")).strip()
        )
        download_path = video.get("download_path", ".")

        # Check if marked as completed in state file
        if vid_id in completed:
            logger.log(
                f"Skipping already completed lecture (state): {video['title']}",
                status=logger.Status.INFO,
            )
            continue

        # If final file already exists on disk, mark completed and skip
        # We check common extensions (mp4) and any other typical ones if needed.
        final_mp4 = os.path.join(download_path, f"{expected_basename}.mp4")
        if os.path.isfile(final_mp4) and os.path.getsize(final_mp4) > 0:
            logger.log(
                f"Skipping already downloaded file: {final_mp4}",
                status=logger.Status.INFO,
            )
            completed.add(vid_id)
            _save_course_state(course_root, {"completed": list(completed)})
            continue

        try:
            logger.log(f"Processing: {video['title']}", status=logger.Status.INFO)
            # Clean leftover temporary files that might block download
            _cleanup_leftovers_for_target(download_path, expected_basename)

            # Open video in new tab
            self.driver.execute_script(f"window.open('{video['link']}', '_blank');")
            new_window = [
                w for w in self.driver.window_handles if w != original_window
            ][0]
            self.driver.switch_to.window(new_window)
            # Wait for page to load
            _ = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            # Process video in the new tab
            _process_video_in_tab(self, video)

            # After processing, check if the file exists now and mark completed if so
            if os.path.isfile(final_mp4) and os.path.getsize(final_mp4) > 0:
                logger.log(
                    f"Marking lecture as completed: {video['title']}",
                    status=logger.Status.INFO,
                )
                completed.add(vid_id)
                _save_course_state(course_root, {"completed": list(completed)})
            else:
                logger.log(
                    f"Lecture not present after processing: {video['title']}",
                    status=logger.Status.WARNING,
                )

        except Exception as e:
            logger.log(f"Failed {video['title']}: {e}", status=logger.Status.ERROR)
        finally:
            # Close the tab and return to original window
            self = _safe_close_current_tab(self, original_window)
    return self


def _process_video_in_tab(self: "TeachableDownloader", video) -> "TeachableDownloader":
    """Process a single video tab (unchanged other than being used by resume logic)."""
    # Save HTML
    self.save_webpage_as_html(video["title"], video["idx"], video["download_path"])
    try:
        if download_video_file(
            self, video["title"], video["idx"], video["download_path"]
        ):
            return self  # If direct file download succeeded
    except Exception as e:
        logger.log(
            f"Attachment download failed, proceeding to iframe method: {e}",
            status=logger.Status.WARNING,
        )
    # If not, use iframe method (existing implementation provided elsewhere)
    self = _download_via_iframe_optimized(self, video)
    return self


def _download_via_iframe_optimized(
    self: "TeachableDownloader", video
) -> "TeachableDownloader":
    """Optimized iframe download helper."""
    # This element exists in other file; keep behavior identical.
    video_iframes = self.driver.find_elements(
        By.XPATH, "//iframe[starts-with(@data-testid, 'embed-player')]"
    )

    for i, iframe in enumerate(video_iframes):
        try:
            self.driver.switch_to.frame(iframe)

            # Extract video link using JavaScript to avoid multiple DOM queries
            link = self.driver.execute_script("""
                try {
                    var script = document.getElementById('__NEXT_DATA__');
                    var data = JSON.parse(script.innerHTML);
                    return data.props.pageProps.applicationData.mediaAssets[0].urlEncrypted;
                } catch(e) {
                    return null;
                }
            """)

            if link:
                video_title = video["title"] + (
                    f"-{i + 1}" if len(video_iframes) > 1 else ""
                )
                # Download subtitle and video in parallel (the caller's implementation)
                self._download_video_and_subs_parallel(
                    link, video_title, video["idx"], video["download_path"]
                )
        except Exception as e:
            logger.log(f"Iframe {i} failed: {e}", status=logger.Status.WARNING)
        finally:
            self.driver.switch_to.default_content()
    return self


def _safe_close_current_tab(
    self: "TeachableDownloader", original_window
) -> "TeachableDownloader":
    """Safely close current tab and switch back to original (unchanged)."""
    try:
        if len(self.driver.window_handles) > 1:
            self.driver.close()
            self.driver.switch_to.window(original_window)
    except Exception as e:
        logger.log(f"Window switch error: {e}", status=logger.Status.WARNING)
        # Reset to first window if possible
        if self.driver.window_handles:
            self.driver.switch_to.window(self.driver.window_handles[0])
    return self
