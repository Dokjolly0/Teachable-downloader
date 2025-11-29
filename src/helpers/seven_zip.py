import os
import shutil
import zipfile

import wget

import src.helpers.logger as logger

link_zip = "https://www.7-zip.org/a/7za920.zip"
bin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "bin")
zip_path = os.path.join(bin_dir, "7za.zip")
exe_path = os.path.join(bin_dir, "7za.exe")
temp_7za_dir = os.path.join(bin_dir, "temp_7za_extract")


def get_7za():
    """Downloads and extracts 7za.exe if it doesn't exist, and returns its path."""
    if not os.path.exists(exe_path):
        logger.log("7za.exe not found. Downloading...", status=logger.Status.INFO)
        os.makedirs(bin_dir, exist_ok=True)
        os.makedirs(temp_7za_dir, exist_ok=True)  # Create temp folder

        zip_path = os.path.join(temp_7za_dir, "7za.zip")

        # Download the ZIP file to the temp folder
        wget.download(link_zip, zip_path)

        try:
            # Extract the ZIP file into the temp folder
            logger.log(f"Extracting {zip_path}...", status=logger.Status.INFO)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_7za_dir)

            # Move only 7za.exe to the final bin_dir
            shutil.move(os.path.join(temp_7za_dir, "7za.exe"), exe_path)
            logger.log("7za.exe installed successfully.", status=logger.Status.INFO)
        except Exception as e:
            logger.log("Failed to extract 7za.zip:", status=logger.Status.ERROR, exc=e)
            raise

        # Clean up the entire temp folder
        shutil.rmtree(temp_7za_dir)

    return exe_path
