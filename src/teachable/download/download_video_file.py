from __future__ import annotations

import glob
import os
import time
from typing import TYPE_CHECKING

from selenium.webdriver.common.by import By

import src.helpers.logger as logger

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader


def _remove_temp_matches(output_path: str):
    """Remove common Chrome temp download files in the output directory."""
    try:
        patterns = ["*.crdownload", "*.part", "*.part-*"]
        for pat in patterns:
            for p in glob.glob(os.path.join(output_path, pat)):
                try:
                    os.remove(p)
                    logger.log(f"Removed temp file {p}", status=logger.Status.DEBUG)
                except Exception as e:
                    logger.log(
                        f"Could not remove temp file {p}: {e}",
                        status=logger.Status.WARNING,
                    )
    except Exception as e:
        logger.log(f"Error cleaning temp files: {e}", status=logger.Status.DEBUG)


def download_video_file(
    self: "TeachableDownloader", title, video_index, output_path, timeout=-1
) -> bool:
    """Attempt to download video via the direct attachment link (browser download).
    This function now supports resume detection:
    - If the final filename exists and is non-zero length it is skipped.
    - Temporary download leftovers are removed before starting.
    """
    video_title = "{:02d}-{}".format(video_index, title)
    final_filename = f"{video_title}.mp4"
    final_filepath = os.path.join(output_path, final_filename)

    # If final file already exists, skip download
    if os.path.isfile(final_filepath) and os.path.getsize(final_filepath) > 0:
        logger.log(
            f"Existing file detected, skipping download: {final_filepath}",
            status=logger.Status.INFO,
        )
        return True

    # Clean leftover temp files before starting
    _remove_temp_matches(output_path)

    # Grab the video attachments type video
    try:
        video_attachment = self.driver.find_element(
            By.CLASS_NAME, "lecture-attachment-type-video"
        )
    except Exception:
        logger.log(
            f"No video attachment element found for lecture: {title}",
            status=logger.Status.DEBUG,
        )
        return False

    if not video_attachment:
        logger.log(
            f"No video attachment found for lecture: {title}",
            status=logger.Status.DEBUG,
        )
        return False

    try:
        video_link = video_attachment.find_element(By.TAG_NAME, "a")
    except Exception:
        logger.log(
            f"No video link found for lecture: {title}", status=logger.Status.DEBUG
        )
        return False

    # Set the download directory for this file (Chrome DevTools Protocol)
    try:
        self.driver.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": output_path},
        )
    except Exception as e:
        logger.log(
            f"Could not set download behavior: {e}", status=logger.Status.WARNING
        )

    # Get list of files before download
    try:
        files_before_download = set(os.listdir(output_path))
    except Exception:
        files_before_download = set()

    # Click the link to trigger download
    try:
        video_link.click()
    except Exception as e:
        logger.log(f"Could not click video link: {e}", status=logger.Status.ERROR)
        return False

    # Wait for download to complete by observing new files and ensuring no temp suffix
    start_time = time.time()
    while True:
        try:
            files_after_download = set(os.listdir(output_path))
        except Exception:
            files_after_download = set()

        new_files = files_after_download - files_before_download

        # If there is exactly one new file and it doesn't end with temp suffixes, we assume done
        if len(new_files) >= 1:
            # pick the largest non-temp file among new_files
            non_temp = [
                f
                for f in new_files
                if not f.endswith(".crdownload")
                and not f.endswith(".part")
                and ".part-" not in f
            ]
            if len(non_temp) == 1:
                latest = non_temp[0]
                latest_file = os.path.join(output_path, latest)
                # Rename it to our final filename if necessary
                try:
                    _, extension = os.path.splitext(latest_file)
                    new_filename = final_filename
                    new_filepath = os.path.join(output_path, new_filename)
                    if latest_file != new_filepath:
                        os.rename(latest_file, new_filepath)
                    logger.log(
                        f"Downloaded video file {new_filename}",
                        status=logger.Status.INFO,
                    )
                    return True
                except Exception as e:
                    logger.log(
                        f"Could not rename downloaded file {latest_file}: {e}",
                        status=logger.Status.WARNING,
                    )
                    # fallback: check if final filepath exists
                    if (
                        os.path.isfile(final_filepath)
                        and os.path.getsize(final_filepath) > 0
                    ):
                        logger.log(
                            f"Final file exists after download attempt: {final_filepath}",
                            status=logger.Status.INFO,
                        )
                        return True
        # Timeout handling
        if timeout > 0 and (time.time() - start_time) > timeout:
            logger.log(
                f"Download timeout for lecture: {title}",
                status=logger.Status.WARNING,
            )
            return False

        time.sleep(1)
    # Unreachable, but keep signature consistent
    return False
