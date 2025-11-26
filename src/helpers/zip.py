import logging
import zipfile


def extract(file_path, destination_folder) -> None:
    """Extracts a zip file to a destination folder.

    Args:
        file_path (str): The path to the zip file.
        destination_folder (str): The path to the destination folder.

    Raises:
        Exception: If the zip file cannot be extracted.
    """
    try:
        with zipfile.ZipFile(file_path, "r") as zip_ref:
            zip_ref.extractall(destination_folder)
    except Exception as e:
        logging.error(f"Failed to extract {file_path}: {e}")
