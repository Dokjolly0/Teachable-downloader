import os
import shutil
import subprocess

import wget

import src.helpers.logger as logger
from src.helpers.zip import extract


def check_ffmpeg_available(ffmpeg_path="./bin/ffmpeg.exe"):
    """Check if ffmpeg is available at the specified path"""
    if os.path.exists(ffmpeg_path):
        logger.log(f"FFmpeg finded in: {ffmpeg_path}", status=logger.Status.INFO)
        return ffmpeg_path
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            logger.log("FFmpeg found in PATH", status=logger.Status.INFO)
            return "ffmpeg"
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    return None


def install_ffmpeg():
    bin_dir = "./bin"
    # Use a temporary directory for extraction, safely outside the final destination
    temp_extract_dir = os.path.join(bin_dir, "temp_ffmpeg_extract")

    try:
        download_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-git-full.7z"
        ffmpeg_7z_path = os.path.join(bin_dir, "ffmpeg.7z")

        os.makedirs(bin_dir, exist_ok=True)
        os.makedirs(temp_extract_dir, exist_ok=True)

        # 1. Download the file
        if not os.path.exists(ffmpeg_7z_path) or os.path.getsize(ffmpeg_7z_path) == 0:
            logger.log(f"Downloading FFmpeg from {download_url}", logger.Status.INFO)
            wget.download(download_url, ffmpeg_7z_path)
        else:
            logger.log("FFmpeg .7z file already downloaded.", logger.Status.INFO)

        # 2. Extract to the TEMPORARY directory
        # The extract function will handle the nested folder creation (e.g. temp_extract_dir/ffmpeg-2025-...)
        logger.log(
            f"Extracting to temporary directory: {temp_extract_dir}", logger.Status.INFO
        )
        extract(ffmpeg_7z_path, temp_extract_dir)  # ***CRITICAL CHANGE***

        # 3. Locate the nested 'bin' folder and move its contents
        # The structure is usually temp_extract_dir/nested_folder/bin/ffmpeg.exe

        # Find the single nested folder (e.g., 'ffmpeg-2025-11-27-git-...')
        nested_folder_name = os.listdir(temp_extract_dir)[0]
        source_bin_dir = os.path.join(temp_extract_dir, nested_folder_name, "bin")

        logger.log("Moving executables to final location...")
        # Move ffmpeg.exe, ffprobe.exe, ffplay.exe from source_bin_dir to bin_dir
        for filename in os.listdir(source_bin_dir):
            if filename.endswith(".exe"):
                shutil.move(
                    os.path.join(source_bin_dir, filename),
                    os.path.join(bin_dir, filename),
                )

        # 4. Clean up the downloaded .7z and the temporary extraction folder
        logger.log("Cleaning up temporary files...", logger.Status.INFO)
        os.remove(ffmpeg_7z_path)
        shutil.rmtree(
            temp_extract_dir
        )  # Use shutil.rmtree to delete the entire folder structure

        logger.log("FFmpeg installed successfully and cleaned up.", logger.Status.INFO)

    except FileNotFoundError as fnfe:
        logger.log(
            f"File system error during install: {fnfe}", status=logger.Status.ERROR
        )
    except subprocess.CalledProcessError:
        logger.log(
            "Failed to install FFmpeg during extraction.", status=logger.Status.ERROR
        )
    except Exception as e:
        # Catch any other unexpected error during file operations
        logger.log(f"An error occurred: {e}", status=logger.Status.ERROR)

    # Final Cleanup: Remove 7-Zip related files from the root /bin directory
    # Note: 7za.exe must be kept, but its associated files should be removed.
    files_to_clean = ["7-zip.chm", "license.txt", "readme.txt"]
    for filename in files_to_clean:
        file_path = os.path.join(bin_dir, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.log(f"Removed 7z helper file: {filename}", logger.Status.INFO)
