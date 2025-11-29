from __future__ import annotations

import os
from typing import TYPE_CHECKING

import wget
from selenium.webdriver.common.by import By

import src.helpers.logger as logger

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader


def download_attachments(
    self: "TeachableDownloader", link, title, video_index, output_path
) -> TeachableDownloader:
    video_title = "{:02d}-{}".format(video_index, title)

    # Grab the video attachments type file
    video_attachments = self.driver.find_elements(
        By.CLASS_NAME, "lecture-attachment-type-file"
    )
    # Get all links from the video attachments

    if video_attachments:
        video_links = video_attachments[0].find_elements(By.TAG_NAME, "a")

        output_path = os.path.join(output_path, video_title)
        os.makedirs(output_path, exist_ok=True)

        # Get href attribute from the first link
        if video_links:
            for video_link in video_links:
                link = video_link.get_attribute("href")
                file_name = video_link.text
                logger.log(
                    "Downloading attachment: " + file_name + " for video: " + title,
                    status=logger.Status.INFO,
                )
                # Download file and save the file in output_path directory
                wget.download(link, out=output_path)
    else:
        logger.log(
            "No attachments found for video: " + title, status=logger.Status.WARNING
        )
    return self
