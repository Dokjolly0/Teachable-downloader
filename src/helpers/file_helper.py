import logging
import os


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
        logging.warning("Truncating title: " + turncated_title)
        return turncated_title
    return title


def clean_string(data):
    logging.debug("Cleaning string: " + data)
    # Remove all non-ASCII characters (including emojis)
    data = data.encode("ascii", "ignore").decode("ascii")
    # Replace specific characters with char '-'
    char: str = "-"
    return (
        data.replace("\n", char)
        .replace(" ", char)
        .replace(":", char)
        .replace("/", char)
        .replace("|", char)
        .replace("*", "")
        .replace("?", char)
        .replace("<", char)
        .replace(">", char)
        .replace('"', char)
        .replace("\\", char)
    )
