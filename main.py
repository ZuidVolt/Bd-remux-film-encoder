# main.py
import subprocess
import time
from pathlib import Path
import os
import argparse
from dotenv import load_dotenv
from env_file_handler import check_env_file
from video_processor import VideoProcessor
from custom_logger import CustomLogger as Logger
from validate import validate_encoding_setup
from utils import EncodingPreset, EncodingConfig, EncodingPresetVideotoolbox


# Create a custom logger
logger = Logger(__name__)


def get_file_paths() -> tuple[Path, Path]:
    """
    Get input and output file paths. For command line input, output path is automatically
    generated in a 'finished' subdirectory. For environment variables, both paths must be specified.

    Returns:
        tuple[Path, Path]: Input file path and output file path
    """
    parser = argparse.ArgumentParser(description="Process and encode video files")
    parser.add_argument("--input", "-i", help="Input video file path")
    args = parser.parse_args()

    # If command line input is provided, use it and create output path
    if args.input:
        input_path = Path(args.input).resolve()
        # Create output directory as 'finished' in the same directory as input file
        output_dir = input_path.parent / "finished"
        output_dir.mkdir(parents=True, exist_ok=True)
        # Use same filename in the output directory
        output_path = output_dir / input_path.name
        return input_path, output_path

    # Otherwise, fall back to environment variables
    logger.info("No command line arguments provided, falling back to environment variables")
    check_env_file()
    load_dotenv()

    input_file_path = os.getenv("INPUT_FILE")
    output_file_path = os.getenv("OUTPUT_FILE")

    if input_file_path is None or output_file_path is None:
        raise ValueError(
            "Either provide input path via command line or set both INPUT_FILE and OUTPUT_FILE environment variables",
        )

    return Path(input_file_path), Path(output_file_path)


def main() -> None:
    start_time = time.time()
    try:
        logger.info("=== Starting Video Processing ===")

        # Create optimized configuration
        config = EncodingConfig(
            target_size_gb=4.0,
            maintain_dolby_vision=True,
            copy_audio=True,
            copy_subtitles=True,
            english_audio_only=True,
            english_subtitles_only=True,
            use_hardware_acceleration=True,
            hardware_encoder="hevc_videotoolbox",
            quality_preset=EncodingPresetVideotoolbox.SLOW,
            allow_sw_fallback=True,
            realtime="false",
            min_video_bitrate=8_000_000,  # 8 Mbps
            max_video_bitrate=30_000_000,  # 30 Mbps
            b_frames="4",
            profile_v="main10",
            max_ref_frames="6",
            group_of_pictures="120",
            # extra params
            audio_bitrate="768k",  # Specify the bitrate for the TrueHD stream
            audio_codec="eac3",  # this is a backup if audio copy doesnt work
            audio_channel="6",  # Set to 8 for 7.1 surround sound # TODO: make this work
            # x265 params (only when videotoolbox doesnt work)
            preset=EncodingPreset.VERYSLOW,
            hdr_params={
                "max_cll": "1600,400",
                "master_display": "G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,50)",
            },
        )

        # Get input and output paths
        input_file, output_file = get_file_paths()

        # Validate input file
        if not input_file.exists():
            raise FileNotFoundError(f"Input file does not exist: {input_file}")
        if not os.access(input_file, os.R_OK):
            raise PermissionError(f"Cannot read input file: {input_file}")
        if not validate_encoding_setup(input_file, output_file, config):
            logger.error("Validation failed. Exiting.")
            return
        logger.info("=== Configuration Settings ===")
        logger.info(f"Input File: {input_file}")
        logger.info(f"Output File: {output_file}")
        logger.info(f"Target Size: {config.target_size_gb} GB")
        logger.info(f"Encoding Preset: {config.preset.value}")
        logger.info(f"Hardware Acceleration: {'Enabled' if config.use_hardware_acceleration else 'Disabled'}")
        logger.info(f"Hardware Encoder: {config.hardware_encoder}")
        logger.info(f"Quality Preset: {config.quality_preset}")
        logger.info(f"Audio Settings: {config.audio_codec} @ {config.audio_bitrate}")
        logger.info(
            f"Language Filters: English Audio Only: {config.english_audio_only}, "
            f"English Subtitles Only: {config.english_subtitles_only}",
        )

        # Check system capabilities
        logger.info("=== System Check ===")
        for tool in ["ffmpeg", "ffprobe"]:
            version = subprocess.check_output([tool, "-version"]).decode().split("\n")[0]
            logger.info(f"{tool.upper()} Version: {version}")

        # Initialize processor
        processor = VideoProcessor(input_file, config)

        # Analyze input
        logger.info("=== Input Analysis ===")
        probe_data = processor.probe_file()
        logger.log_input_analysis(probe_data)

        # Start encoding
        target_bitrate = processor.calculate_bitrate()
        cmd = processor.build_command(output_file, target_bitrate)
        logger.log_encoding_start(output_file, target_bitrate, cmd)
        logger.log_estimated_duration(processor.duration)
        encoding_start_time = time.time()
        processor.encode(output_file)
        encoding_duration = time.time() - encoding_start_time

        # Log encoding complete
        logger.log_encoding_complete(input_file, output_file, encoding_duration)

        # Verify output file integrity
        logger.log_verification(output_file)

        # Log final stats
        logger.log_final_stats(start_time)

    except Exception as err:
        logger.error("\n=== Processing Failed ===")
        logger.error(f"Error: {err!s}")
        logger.error("Stack trace:", exc_info=True)
        raise


if __name__ == "__main__":
    main()
