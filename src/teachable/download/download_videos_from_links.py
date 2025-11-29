from __future__ import annotations

from typing import TYPE_CHECKING

import selenium.webdriver.support.expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

import src.helpers.logger as logger
from src.teachable.download.download_video_file import download_video_file

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader


def download_videos_from_links(
    self: "TeachableDownloader", video_list
) -> TeachableDownloader:
    """Version optimized for faster downloads"""
    original_window = self.driver.current_window_handle

    for video in video_list:
        try:
            logger.log(f"Processing: {video['title']}", status=logger.Status.INFO)
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

        except Exception as e:
            logger.log(f"Failed {video['title']}: {e}", status=logger.Status.ERROR)
        finally:
            # Close the tab and return to original window
            self = _safe_close_current_tab(self, original_window)
    return self


def _process_video_in_tab(self: "TeachableDownloader", video) -> TeachableDownloader:
    """Processa un singolo video nella scheda corrente"""
    # Save HTML
    self.save_webpage_as_html(video["title"], video["idx"], video["download_path"])
    try:
        if download_video_file(
            self, video["title"], video["idx"], video["download_path"]
        ):
            return self  # If works, no need to proceed further
    except Exception as e:
        logger.log(
            f"Attachment download failed, proceeding to iframe method: {e}",
            status=logger.Status.WARNING,
        )
    # If not, use iframe method
    self = _download_via_iframe_optimized(self, video)
    return self


def _download_via_iframe_optimized(
    self: "TeachableDownloader", video
) -> TeachableDownloader:
    """Versione ottimizzata del download via iframe"""
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
                # Download subtitle and video in parallel
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
) -> TeachableDownloader:
    """Chiudi scheda corrente in modo sicuro"""
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
