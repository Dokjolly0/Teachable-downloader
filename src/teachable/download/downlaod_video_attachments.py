from __future__ import annotations

import os
from typing import TYPE_CHECKING

import requests
from selenium.webdriver.common.by import By

import src.helpers.logger as logger

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader


def download_attachments(
    self: "TeachableDownloader", link, title, video_index, output_path
) -> TeachableDownloader:
    video_title = "{:02d}-{}".format(video_index, title)

    video_attachments = self.driver.find_elements(
        By.CLASS_NAME, "lecture-attachment-type-file"
    )

    if video_attachments:
        video_links = video_attachments[0].find_elements(By.TAG_NAME, "a")
        output_dir = os.path.join(output_path, video_title)
        os.makedirs(output_dir, exist_ok=True)

        for video_link in video_links:
            file_url = video_link.get_attribute("href")
            file_name = video_link.text

            if not file_url:
                continue

            logger.log(
                f"Downloading attachment: {file_name}", status=logger.Status.INFO
            )

            # Use requests to download the file
            try:
                response = requests.get(
                    file_url, headers=self.headers, timeout=30, stream=True
                )
                response.raise_for_status()

                file_path = os.path.join(output_dir, file_name)
                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                logger.log(f"Downloaded: {file_name}", status=logger.Status.INFO)

            except Exception as e:
                logger.log(
                    f"Failed to download {file_name}:",
                    status=logger.Status.WARNING,
                    exc=e,
                )

    else:
        logger.log(f"No attachments for: {title}", status=logger.Status.DEBUG)

    return self
