# env_file_handler.py
from pathlib import Path
from custom_logger import CustomLogger as Logger

logger = Logger(__name__)


def check_env_file() -> None:
    """
    Creates a new .env file in the current directory if it doesn't exist.
    """
    env_file_path = Path(".env")

    # Check if .env file exists in the current directory
    if not env_file_path.exists():
        try:
            logger.info("Creating new .env file...")
            # Create a new .env file if it doesn't exist
            with env_file_path.open("w", encoding="utf-8") as f:
                f.write("INPUT_FILE=\n")
                f.write("OUTPUT_FILE=\n")
            logger.info(".env file created successfully.")
            logger.info("Please fill in the INPUT_FILE and OUTPUT_FILE variables in the .env file.")
        except PermissionError:
            logger.error("Permission denied to create .env file in the current directory.")
        except OSError as e:
            logger.error(f"An error occurred while creating the .env file: {e}")
    else:
        logger.info(".env file already exists.")


def get_current_directory() -> Path:
    """
    Returns the current working directory.
    """
    return Path.cwd()


def main() -> None:
    logger.info(f"Current directory: {get_current_directory()}")
    check_env_file()


if __name__ == "__main__":
    main()
