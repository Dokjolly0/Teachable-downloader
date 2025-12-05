"""
Factory for creating appropriate course downloaders based on page structure.
"""

from typing import Optional

from selenium.webdriver.common.by import By

import src.helpers.logger as logger
from src.teachable.download.course_downloader_base import BaseCourseDownloader
from src.teachable.download.course_type.download_course_classic import (
    ClassicCourseDownloader,
)
from src.teachable.download.course_type.download_course_colossal import (
    ColossalCourseDownloader,
)
from src.teachable.download.course_type.download_course_simple import (
    SimpleCourseDownloader,
)


class CourseDownloaderFactory:
    """Factory to create appropriate course downloader based on page structure."""

    @staticmethod
    def create_downloader(driver_wrapper) -> Optional[BaseCourseDownloader]:
        """Create appropriate downloader based on page structure."""
        driver = driver_wrapper.driver

        # Check for different course formats
        if driver.find_elements(By.ID, "__next"):
            logger.log("Choosing simple format downloader", status=logger.Status.INFO)
            return SimpleCourseDownloader(driver_wrapper)
        elif driver.find_elements(By.CLASS_NAME, "course-mainbar"):
            logger.log("Choosing classic format downloader", status=logger.Status.INFO)
            return ClassicCourseDownloader(driver_wrapper)
        elif driver.find_elements(By.CSS_SELECTOR, ".block__curriculum"):
            logger.log("Choosing colossal format downloader", status=logger.Status.INFO)
            return ColossalCourseDownloader(driver_wrapper)

        return None
