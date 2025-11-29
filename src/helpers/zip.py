import subprocess
import zipfile

import src.helpers.logger as logger
from src.helpers.seven_zip import get_7za


def extract(file_path, destination_folder) -> None:
    """Extracts a compressed file (.zip or .7z) to a destination folder."""
    try:
        if file_path.endswith(".7z"):
            logger.log(
                f"Attempting to extract {file_path} using 7za.exe.",
                status=logger.Status.INFO,
            )

            # 1. Get the path to the 7z executable
            seven_zip_exe = get_7za()

            # 2. Execute 7za.exe via subprocess
            # Command: 7za.exe x <archive_path> -o<output_directory> -y
            command = [
                seven_zip_exe,
                "x",  # 'x' command: Extract with full paths
                file_path,
                f"-o{destination_folder}",  # Specifies the output directory
                "-y",  # Assumes Yes to all prompts (overwrite files)
            ]

            # Run the command and check the return code
            subprocess.run(command, check=True, capture_output=True, text=True)
            logger.log("Extraction complete via 7za.exe.", status=logger.Status.INFO)

        elif file_path.endswith(".zip"):
            # Fallback to zipfile for .zip files
            logger.log(
                f"Attempting to extract {file_path} using zipfile.",
                status=logger.Status.INFO,
            )
            with zipfile.ZipFile(file_path, "r") as zip_ref:
                zip_ref.extractall(destination_folder)
        else:
            logger.log(
                f"Unsupported file type for extraction: {file_path}",
                status=logger.Status.ERROR,
            )

    except subprocess.CalledProcessError as cpe:
        logger.log(
            f"7za extraction failed (Code {cpe.returncode}). Check if 7za.exe is in PATH.",
            status=logger.Status.ERROR,
        )
        logger.log(f"STDOUT: {cpe.stdout}", status=logger.Status.ERROR)
        logger.log(f"STDERR: {cpe.stderr}", status=logger.Status.ERROR)
    except Exception as e:
        logger.log("Failed to extract {file_path}:", status=logger.Status.ERROR, exc=e)
