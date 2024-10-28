import subprocess
import time
from pathlib import Path
import os
from dotenv import load_dotenv
from env_file_handler import check_env_file
from video_processor import VideoProcessor
from custom_logger import CustomLogger
from utils import EncodingPreset, EncodingConfig


# Create a custom logger
logger = CustomLogger(__name__)


def main() -> None:  # noqa: C901
    start_time = time.time()
    try:
        logger.info("=== Starting Video Processing ===")

        # Create optimized configuration
        config = EncodingConfig(
            target_size_gb=8.0,
            maintain_dolby_vision=True,
            copy_audio=True,
            copy_subtitles=True,
            english_audio_only=True,
            english_subtitles_only=True,
            use_hardware_acceleration=True,
            hardware_encoder="hevc_videotoolbox",
            quality_preset="slow",
            allow_sw_fallback=True,
            audio_bitrate="768k",  # Specify the bitrate for the TrueHD stream
            realtime="false",
            min_video_bitrate=8_000_000,  # 8 Mbps
            max_video_bitrate=30_000_000,  # 30 Mbps
            # extra params
            audio_codec="eac3",  # this is a backup if audio copy doesnt work
            audio_channel="6",  # Set to 8 for 7.1 surround sound # TODO: make this work
            # x265 params (only when videotoolbox doesnt work)
            preset=EncodingPreset.VERYSLOW,
            hdr_params={
                "max_cll": "1600,400",
                "master_display": "G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,50)",
            },
        )

        # Setup paths
        check_env_file()
        load_dotenv()

        input_file_path: str = os.getenv("INPUT_FILE")  # type: ignore
        output_file_path: str = os.getenv("OUTPUT_FILE")  # type: ignore

        if input_file_path is None or output_file_path is None:
            raise ValueError("INPUT_FILE and OUTPUT_FILE environment variables must be set")

        input_file: Path = Path(input_file_path)
        output_file: Path = Path(output_file_path)

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
            f"English Subtitles Only: {config.english_subtitles_only}"
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

        # Log video stream info
        video_stream = next((s for s in probe_data["streams"] if s["codec_type"] == "video"), None)
        if video_stream:
            logger.info("Video Stream Information:")
            logger.info(f"Codec: {video_stream.get('codec_name', 'unknown')}")
            logger.info(f"Resolution: {video_stream.get('width', '?')}x{video_stream.get('height', '?')}")
            logger.info(f"Pixel Format: {video_stream.get('pix_fmt', 'unknown')}")
            logger.info(f"Color Space: {video_stream.get('color_space', 'unknown')}")
            logger.info(f"Color Transfer: {video_stream.get('color_transfer', 'unknown')}")
            logger.info(f"Frame Rate: {video_stream.get('r_frame_rate', 'unknown')}")
            logger.info(f"Bit Depth: {video_stream.get('bits_per_raw_sample', 'unknown')}")

        # Log audio streams
        audio_streams = [s for s in probe_data["streams"] if s["codec_type"] == "audio"]
        logger.info(f"\nFound {len(audio_streams)} audio stream(s):")
        for idx, stream in enumerate(audio_streams):
            language = stream.get("tags", {}).get("language", "unknown")
            codec = stream.get("codec_name", "unknown")
            channels = stream.get("channels", "unknown")
            logger.info(f"Audio Stream {idx + 1}: {codec}, {channels} channels, Language: {language}")

        # Log subtitle streams
        subtitle_streams = [s for s in probe_data["streams"] if s["codec_type"] == "subtitle"]
        logger.info(f"\nFound {len(subtitle_streams)} subtitle stream(s):")
        for idx, stream in enumerate(subtitle_streams):
            language = stream.get("tags", {}).get("language", "unknown")
            codec = stream.get("codec_name", "unknown")
            logger.info(f"Subtitle Stream {idx + 1}: {codec}, Language: {language}")

        # Start encoding
        logger.info("\n=== Starting Encoding Process ===")
        encoding_start_time = time.time()
        target_bitrate = processor._calculate_bitrate()
        cmd = processor._build_command(output_file, target_bitrate)
        logger.info("FFmpeg Command:")
        logger.info(" ".join(cmd))
        processor.encode(output_file)
        encoding_duration = time.time() - encoding_start_time

        # Final statistics
        if output_file.exists():
            input_size = input_file.stat().st_size / (1024 * 1024 * 1024)  # GB
            output_size = output_file.stat().st_size / (1024 * 1024 * 1024)  # GB
            compression_ratio = input_size / output_size if output_size > 0 else 0

            logger.info("\n=== Encoding Complete ===")
            logger.info(f"Input Size: {input_size:.2f} GB")
            logger.info(f"Output Size: {output_size:.2f} GB")
            logger.info(f"Compression Ratio: {compression_ratio:.2f}:1")
            logger.info(f"Encoding Duration: {encoding_duration/3600:.2f} hours")
            logger.info(f"Average Processing Speed: {(input_size*1024)/(encoding_duration/60):.2f} MB/minute")

            # Verify output file integrity
            logger.info("\n=== Verifying Output File ===")
            verify_cmd = ["ffprobe", "-v", "error", "-i", str(output_file), "-show_streams", "-show_format"]
            try:
                verify_output = subprocess.run(verify_cmd, check=True, capture_output=True, text=True)
                if verify_output.stderr:
                    logger.warning("Output file verification: WARNING")
                    logger.warning(verify_output.stderr.strip())
                else:
                    logger.info("Output file verification: PASSED")
            except subprocess.CalledProcessError as e:
                logger.error("Output file verification: FAILED")
                logger.error(f"Command: {' '.join(e.cmd)}")
                logger.error(f"Return code: {e.returncode}")
                if e.stderr:
                    logger.error(e.stderr.strip())
                logger.error("Ignoring verification error and continuing...")

        total_duration = time.time() - start_time
        logger.info(f"\nTotal Processing Time: {total_duration/3600:.2f} hours")
        logger.info("=== Processing Completed Successfully ===")

    except Exception as err:
        logger.error(f"\n=== Processing Failed ===")  # noqa: F541
        logger.error(f"Error: {err!s}")
        logger.error("Stack trace:", exc_info=True)
        raise


if __name__ == "__main__":
    main()
