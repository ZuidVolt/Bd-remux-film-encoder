# validate.py
from pathlib import Path
import shutil
import psutil  # type: ignore
import subprocess
from custom_logger import CustomLogger as Logger
from utils import EncodingConfig
import os


logger = Logger(__name__)

# Constants
MIN_REQUIRED_MEMORY = 4 * 1024 * 1024 * 1024  # 4 GB
MIN_BITRATE = 1_000_000  # 1 Mbps
MAX_BITRATE = 30_000_000  # 30 Mbps
MIN_VALID_SIZE = 100 * 1024 * 1024  # 100 MB
MIN_HEADER_LENGTH = 8  # Minimum length required for most video file signatures


def log_warning(message: str) -> None:
    logger.warning(message)


def log_error(message: str) -> None:
    logger.error(message)


def log_error_and_return_false(message: str) -> bool:
    logger.error(message)
    return False


def validate_encoder_name(encoder_name: str) -> bool:
    if not isinstance(encoder_name, str) or not encoder_name.strip():
        return log_error_and_return_false("Invalid encoder name")
    return True


def is_hardware_encoder_available(encoder_name: str) -> bool:
    """Check if the hardware encoder is available."""
    try:
        output = subprocess.check_output(["ffmpeg", "-encoders"], stderr=subprocess.STDOUT).decode("utf-8")
        if encoder_name not in output:
            return log_error_and_return_false(f"Encoder {encoder_name} not found in ffmpeg output.")
        return True
    except FileNotFoundError:
        return log_error_and_return_false("ffmpeg not found. Ensure it is installed and available in the PATH.")
    except subprocess.CalledProcessError as e:
        return log_error_and_return_false(f"Error executing ffmpeg: {e.output.decode('utf-8')}")
    except Exception as e:
        return log_error_and_return_false(f"Unexpected error while checking hardware encoder: {e}")


def is_valid_video_header(header: bytes) -> bool:
    """Check if the file header is a valid video header."""
    # Common video file signatures
    signatures = {
        "mkv": b"\x1a\x45\xdf\xa3",
        "mp4": b"ftyp",
        "avi": b"RIFF",
        "mov": b"moov",
    }

    if len(header) < MIN_HEADER_LENGTH:  # Need at least MIN_HEADER_LENGTH bytes for most signatures
        return log_error_and_return_false("File header is too short to determine validity.")

    # Check for MKV signature at start
    if header.startswith(signatures["mkv"]):
        return True

    # Check for MP4/MOV signatures (they can appear slightly offset)
    if any(sig in header[:MIN_HEADER_LENGTH] for sig in [signatures["mp4"], signatures["mov"]]):
        return True

    # Check for AVI signature
    if header.startswith(signatures["avi"]):
        return True

    return log_error_and_return_false("File header does not match any known video format signatures.")


def validate_system_resources(input_file: Path, output_file: Path) -> None:
    """Validate system resources before encoding."""
    try:
        # Get the parent directory of the output file for disk space check
        output_dir = output_file.parent
        file_size = input_file.stat().st_size
        free_space = shutil.disk_usage(output_dir).free
        available_memory = psutil.virtual_memory().available

        if free_space <= file_size * 2:
            log_warning(
                "Insufficient disk space for processing. Recommended: at least double the input file size.",
            )

        if available_memory <= MIN_REQUIRED_MEMORY:
            log_warning(
                f"Low memory available. Recommended: {MIN_REQUIRED_MEMORY / (1024**3)} GB or more. "
                "Processing may be slow or unstable.",
            )

    except (FileNotFoundError, PermissionError) as e:
        log_error(f"Directory error: {e}")
    except Exception as e:
        log_error(f"Unexpected error during resource validation: {e}")


def validate_config(config: EncodingConfig) -> bool:
    """Validate the encoding configuration."""
    try:
        if not is_hardware_encoder_available(config.hardware_encoder):
            logger.warning("Hardware encoder not available, falling back to software encoding.")
            config.use_hardware_acceleration = False

        if not MIN_BITRATE <= config.min_video_bitrate <= MAX_BITRATE:
            raise ValueError(
                f"Invalid bitrate: {config.min_video_bitrate}. Must be between {MIN_BITRATE} and {MAX_BITRATE}.",
            )

        return True
    except (AttributeError, ValueError) as e:
        return log_error_and_return_false(f"Configuration validation error: {e}")
    except Exception as e:
        return log_error_and_return_false(f"Unexpected error during configuration validation: {e}")


def validate_input_file(file_path: Path) -> bool:
    """Validate the input video file."""
    valid_extensions = [".mkv", ".mp4", ".avi", ".mov"]

    try:
        if not file_path.exists():
            return log_error_and_return_false(f"Input file does not exist: {file_path}")

        if not file_path.is_file():
            return log_error_and_return_false(f"Path is not a file: {file_path}")

        if file_path.suffix.lower() not in valid_extensions:
            return log_error_and_return_false(
                f"Invalid file type: {file_path}. Supported extensions: {', '.join(valid_extensions)}",
            )

        if file_path.stat().st_size < MIN_VALID_SIZE:
            return log_error_and_return_false(f"File too small to be a valid video: {file_path}")

        try:
            with file_path.open("rb") as f:
                header = f.read(4096)
                if not is_valid_video_header(header):
                    return log_error_and_return_false(f"Invalid video header in file: {file_path}")
        except PermissionError:
            return log_error_and_return_false(f"Permission denied: Cannot read file {file_path}")

        return True
    except Exception as e:
        return log_error_and_return_false(f"Unexpected error validating input file: {e}")


def validate_output_path(output_path: Path) -> bool:
    """Validate the output file path."""
    try:
        # Check if parent directory exists or can be created
        output_dir = output_path.parent
        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                return log_error_and_return_false(f"Permission denied: Cannot create output directory {output_dir}")
            except Exception as e:
                return log_error_and_return_false(f"Error creating output directory: {e}")

        # Check if we can write to the directory
        if not os.access(output_dir, os.W_OK):
            return log_error_and_return_false(f"Permission denied: Cannot write to output directory {output_dir}")

        # Check if output file already exists
        if output_path.exists():
            log_warning(f"Output file already exists: {output_path}")

        return True
    except Exception as e:
        return log_error_and_return_false(f"Unexpected error validating output path: {e}")


def validate_encoding_setup(input_file: Path, output_file: Path, config: EncodingConfig) -> bool:
    """
    Validate the complete encoding setup including input file, output path, system resources,
    and encoding configuration.

    Args:
        input_file (Path): The input video file path
        output_file (Path): The output file path
        config (EncodingConfig): The encoding configuration

    Returns:
        bool: True if all validations pass, False otherwise
    """
    try:
        logger.info("Starting validation checks...")

        # Validate input file
        if not validate_input_file(input_file):
            return False

        # Validate output path
        if not validate_output_path(output_file):
            return False

        # Validate system resources
        validate_system_resources(input_file, output_file)

        # Validate encoding configuration
        if not validate_config(config):
            return False

        logger.info("All validation checks passed successfully.")
        return True

    except Exception as e:
        return log_error_and_return_false(f"Unexpected error during validation: {e}")
