from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from selenium.webdriver.common.by import By

import src.helpers.logger as logger

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader


def download_video_file(
    self: "TeachableDownloader", title, video_index, output_path, timeout=-1
) -> bool:
    video_title = "{:02d}-{}".format(video_index, title)

    # Grab the video attachments type video
    video_attachment = self.driver.find_element(
        By.CLASS_NAME, "lecture-attachment-type-video"
    )

    if not video_attachment:
        logger.log(
            f"No video attachment found for lecture: {title}",
            status=logger.Status.DEBUG,
        )
        return False

    video_link = video_attachment.find_element(By.TAG_NAME, "a")

    if not video_link:
        logger.log(
            f"No video link found for lecture: {title}", status=logger.Status.DEBUG
        )
        return False

    # Set the download directory for this file
    self.driver.execute_cdp_cmd(
        "Page.setDownloadBehavior",
        {"behavior": "allow", "downloadPath": output_path},
    )
    # Get list of files before download
    files_before_download = set(os.listdir(output_path))

    # Click the link to trigger download
    video_link.click()

    # Wait for download to complete
    start_time = time.time()
    while True:
        files_after_download = set(os.listdir(output_path))

        # Find new files
        new_files = files_after_download - files_before_download

        if len(new_files) == 1 and not list(new_files)[0].endswith(".crdownload"):
            break

        if timeout > 0 and (time.time() - start_time) > timeout:
            logger.log(
                f"Download timeout for lecture: {title}",
                status=logger.Status.WARNING,
            )
            return False

        time.sleep(1)

    latest_file = os.path.join(output_path, list(new_files)[0])

    # Determine the file extension
    _, extension = os.path.splitext(latest_file)

    # Create the new filename
    new_filename = f"{video_title}{extension}"
    new_filepath = os.path.join(output_path, new_filename)

    # Rename the file
    os.rename(latest_file, new_filepath)
    logger.log(f"Downloaded video file {new_filename}", status=logger.Status.INFO)
    return True
