from __future__ import annotations

import json
from typing import TYPE_CHECKING

from selenium.webdriver.common.by import By

import src.helpers.logger as logger
from src.teachable.download.downlaod_video_attachments import download_attachments
from src.teachable.download.download_subtitle import download_subtitle
from src.teachable.download.download_video import download_video
from src.teachable.download.download_video_file import download_video_file

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader


def download_videos_from_links(
    self: "TeachableDownloader", video_list
) -> TeachableDownloader:
    for video in video_list:
        if self.driver.current_url != video["link"]:
            logger.log(
                "Navigating to lecture: " + video["title"],
                status=logger.Status.INFO,
            )
            self.driver.get(video["link"])
            self.driver.implicitly_wait(self.global_timeout)
        logger.log("Downloading lecture: " + video["title"], status=logger.Status.INFO)

        # logger.log("Disabling autoplay", status=logger.Status.INFO)
        # self.driver.execute_script('var checkbox = document.getElementById("custom-toggle-autoplay");'
        #                            'if (checkbox.checked) {checkbox.click();}')

        try:
            logger.log("Saving html", status=logger.Status.INFO)
            self.save_webpage_as_html(
                video["title"], video["idx"], video["download_path"]
            )
        except Exception as e:
            logger.log(
                f"Could not save html: {video['title']} cause: {e}",
                status=logger.Status.WARNING,
            )

        try:
            logger.log("Downloading attachments", status=logger.Status.INFO)
            self = download_attachments(
                self,
                video["link"],
                video["title"],
                video["idx"],
                video["download_path"],
            )
        except Exception as e:
            logger.log(
                f"Could not download attachments: {video['title']} cause: {e}",
                status=logger.Status.WARNING,
            )

        try:
            logger.log(
                "Trying to download video as an attachment",
                status=logger.Status.DEBUG,
            )
            if download_video_file(
                self, video["title"], video["idx"], video["download_path"]
            ):
                continue

        except Exception as e:
            logger.log(
                f"Could not download video as an attachment: {video['title']} cause: {e}",
                status=logger.Status.WARNING,
            )

        video_iframes = self.driver.find_elements(
            By.XPATH, "//iframe[starts-with(@data-testid, 'embed-player')]"
        )

        for i, iframe in enumerate(video_iframes):
            try:
                logger.log("Switching to video frame", status=logger.Status.INFO)
                self.driver.switch_to.frame(iframe)

                script_text = self.driver.find_element(By.ID, "__NEXT_DATA__")
                json_text = json.loads(script_text.get_attribute("innerHTML"))
                link = json_text["props"]["pageProps"]["applicationData"][
                    "mediaAssets"
                ][0]["urlEncrypted"]

                # Append -n to the video title if there are multiple iframes
                video_title = video["title"] + (
                    "-" + str(i + 1) if len(video_iframes) > 1 else ""
                )

                try:
                    logger.log("Downloading subtitle", status=logger.Status.INFO)
                    self = download_subtitle(
                        self,
                        link,
                        video_title,
                        video["idx"],
                        video["download_path"],
                    )
                except Exception as e:
                    logger.log(
                        f"Could not download subtitle: {video_title} cause: {e}",
                        status=logger.Status.WARNING,
                    )

                try:
                    logger.log("Downloading video", status=logger.Status.INFO)
                    self = download_video(
                        self,
                        link,
                        video_title,
                        video["idx"],
                        video["download_path"],
                    )
                except Exception as e:
                    logger.log(
                        f"Could not download video: {video_title} cause: {e}",
                        status=logger.Status.WARNING,
                    )

                self.driver.switch_to.default_content()  # Switch back to main content before the next iteration

            except Exception as e:
                logger.log(
                    f"Could not find video: {video['title']} cause: {e}",
                    status=logger.Status.WARNING,
                )
                continue

        logger.log("Downloaded video: " + video["title"], status=logger.Status.INFO)

        if self._complete_lecture:
            try:
                logger.log("Completing lecture", status=logger.Status.INFO)
                self.complete_lecture()
            except Exception as e:
                logger.log(
                    f"Could not complete lecture: {video['title']} cause: {e}",
                    status=logger.Status.WARNING,
                )

    return self
