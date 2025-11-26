import logging
import os
import subprocess

import wget

from src.helpers.zip import extract


def check_ffmpeg_available(ffmpeg_path="./bin/ffmpeg.exe"):
    """Check if ffmpeg is available at the specified path"""
    if os.path.exists(ffmpeg_path):
        logging.info(f"✅ FFmpeg trovato in: {ffmpeg_path}")
        return ffmpeg_path
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            logging.info("FFmpeg found in PATH")
            return "ffmpeg"
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    return None


def install_ffmpeg():
    try:
        download_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-git-full.7z"
        ffmpeg_7z_path = "./bin/ffmpeg.7z"
        os.makedirs("./bin", exist_ok=True)
        wget.download(download_url, ffmpeg_7z_path)
        extract(ffmpeg_7z_path, "./bin/ffmpeg.exe")
        os.remove(ffmpeg_7z_path)
        logging.info("FFmpeg installed successfully")
    except subprocess.CalledProcessError:
        logging.error("Failed to install FFmpeg")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
