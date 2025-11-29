import os
import re

import src.helpers.logger as logger


def create_course_folder(course_title):
    """Create a folder for a course."""
    root_path = os.path.abspath(os.getcwd())
    course_path = os.path.join(root_path, "downloads", "courses", course_title)
    os.makedirs(course_path, exist_ok=True)
    return course_path


def truncate_title_to_fit_file_name(title, max_file_name_length=250):
    """Truncate the title to fit the file name length."""
    # the file name length should not be too long
    # truncate the title to accommodate the max used file extension length and lecture index prefix
    max_title_length = max_file_name_length - len(".mp4.part-Frag0000.part") - 3
    if len(title) > max_title_length:
        turncated_title = title[:max_title_length]
        logger.log("Truncating title: " + turncated_title, logger.Status.WARNING)
        return turncated_title
    return title


def clean_string(data):
    logger.log("Cleaning string: " + data, logger.Status.INFO)
    # Mantieni solo ASCII
    data = data.encode("ascii", "ignore").decode("ascii")
    # Remove invalid filename characters
    invalid = [":", "/", "|", "*", "?", "<", ">", '"', "\\"]
    for ch in invalid:
        data = data.replace(ch, "")
    # Replace new lines with spaces and trim leading/trailing spaces
    data = data.replace("\n", " ").strip()
    return data


def read_urls_from_file(file_path):
    urls = []
    try:
        with open(file_path, "r") as file:
            urls = file.read().splitlines()
    except FileNotFoundError:
        logger.log(f"File not found: {file_path}", logger.Status.ERROR)
    except IOError as e:
        logger.log(
            f"IOError reading file: {file_path}. Error: {str(e)}", logger.Status.ERROR
        )
    except Exception as e:
        logger.log(
            f"Unexpected error reading file: {file_path}. Error: {str(e)}",
            logger.Status.ERROR,
        )

    if urls:
        logger.log(
            f"Successfully read {len(urls)} URLs from file: {file_path}",
            logger.Status.INFO,
        )
    else:
        logger.log(f"No URLs found in file: {file_path}", logger.Status.WARNING)

    return urls


def sanitize_for_filename(s: str, max_len=200):
    # Keep basic chars, replace spaces with hyphens, trim length
    if not s:
        return "untitled"
    s = str(s)
    s = re.sub(r'[\/:*?"<>|]', "-", s)  # remove illegal FS chars
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace(" ", "-")
    if len(s) > max_len:
        s = s[:max_len]
    return s
