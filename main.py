import subprocess, json, logging, shutil, sys, re, time  # noqa: E401
from pathlib import Path
from typing import Optional, List, Union, TypedDict, Dict, Any, cast
from enum import Enum
from datetime import datetime
import os
from dotenv import load_dotenv
from env_file_handler import check_env_file


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"encoding_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
    ],
)

logger = logging.getLogger(__name__)


class EncoderError(Exception):
    pass


class ProbeError(EncoderError):
    pass


class EncodingError(EncoderError):
    pass


class EncodingPreset(Enum):
    ULTRAFAST = "ultrafast"
    SUPERFAST = "superfast"
    VERYFAST = "veryfast"
    FASTER = "faster"
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"
    SLOWER = "slower"
    VERYSLOW = "veryslow"


class StreamDict(TypedDict, total=False):
    index: int
    codec_type: str
    codec_name: str
    height: int
    width: int
    color_space: str
    color_transfer: str
    color_primaries: str
    r_frame_rate: str
    tags: Dict[str, str]


class ProbeData(TypedDict):
    streams: List[StreamDict]
    format: Dict[str, Any]


class EncodingConfig:
    def __init__(
        self,
        target_size_gb: float = 25.0,
        preset: EncodingPreset = EncodingPreset.MEDIUM,
        maintain_dolby_vision: bool = True,
        copy_audio: bool = True,
        copy_subtitles: bool = True,
        english_audio_only: bool = False,
        english_subtitles_only: bool = False,
        use_hardware_acceleration: bool = True,
        hardware_encoder: str = "hevc_videotoolbox",
        fallback_encoder: str = "libx265",
        quality_preset: str = "slow",
        allow_sw_fallback: bool = True,
        audio_codec: str = "aac",
        audio_bitrate: str = "384k",
        audio_channel: str = "8",
        min_video_bitrate: int = 8_000_000,  # 8 Mbps
        max_video_bitrate: int = 30_000_000,  # 30 Mbps
        hdr_params: Optional[Dict[str, str]] = None,
        realtime: str = "true",
        b_frames: str = "2",
    ):
        self.target_size_gb = target_size_gb
        self.preset = preset
        self.maintain_dolby_vision = maintain_dolby_vision
        self.copy_audio = copy_audio
        self.copy_subtitles = copy_subtitles
        self.english_audio_only = english_audio_only
        self.english_subtitles_only = english_subtitles_only
        self.use_hardware_acceleration = use_hardware_acceleration
        self.hardware_encoder = hardware_encoder
        self.fallback_encoder = fallback_encoder
        self.quality_preset = quality_preset
        self.allow_sw_fallback = allow_sw_fallback
        self.audio_codec = audio_codec
        self.audio_bitrate = audio_bitrate
        self.audio_channel = audio_channel
        self.min_video_bitrate = min_video_bitrate
        self.max_video_bitrate = max_video_bitrate
        self.hdr_params = hdr_params or {
            "max_cll": "1000,400",
            "master_display": "G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,50)",
        }
        self.realtime = realtime
        self.b_frames = b_frames
        self.min_video_bitrate = min_video_bitrate
        self.max_video_bitrate = max_video_bitrate


class VideoProcessor:
    def __init__(self, input_file: Union[str, Path], config: Optional[EncodingConfig] = None):
        self.input_file = Path(input_file)
        self.config = config or EncodingConfig()
        if not self.input_file.exists() or not self.input_file.is_file():
            raise FileNotFoundError(f"Invalid input file: {self.input_file}")
        if not all(shutil.which(tool) for tool in ["ffmpeg", "ffprobe"]):
            raise OSError("ffmpeg or ffprobe not found in PATH")
        self.probe_data: Optional[ProbeData] = None
        self.input_size_gb: float = 0.0
        self.duration: float = 0.0
        self.hw_support: Optional[bool] = None

    def probe_file(self) -> ProbeData:
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(self.input_file),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            probe_data = json.loads(result.stdout)
            # Ensure the loaded data matches our expected type

            self.probe_data = cast(ProbeData, probe_data)
            format_info = self.probe_data["format"]
            self.input_size_gb = float(format_info["size"]) / (1024**3)
            self.duration = float(format_info["duration"])
            logger.info(f"Input: {self.input_size_gb:.2f}GB, Duration: {self.duration:.2f}s")
            return self.probe_data
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            raise ProbeError(f"Probe failed: {e!s}")  # noqa: B904

    def _get_stream_indexes(self) -> Dict[str, List[int]]:
        if not self.probe_data:
            self.probe_file()

        if not self.probe_data:  # This check is for type checker
            raise ValueError("Probe data is still None after probe_file()")

        indexes: Dict[str, List[int]] = {"video": [], "audio": [], "subtitle": []}
        for stream in self.probe_data["streams"]:
            stream_type = stream.get("codec_type", "")
            if stream_type not in indexes:
                continue

            if (
                self.config.english_audio_only
                and stream_type == "audio"
                or self.config.english_subtitles_only
                and stream_type == "subtitle"
            ):
                tags = stream.get("tags", {})
                if tags.get("language", "").lower() in ["eng", "english"]:
                    indexes[stream_type].append(stream["index"])
            else:
                indexes[stream_type].append(stream["index"])

        return indexes

    def _calculate_bitrate(self) -> int:
        if not self.probe_data or self.duration <= 0:
            raise ValueError("Invalid probe data")

        total_bits = self.config.target_size_gb * 8 * 1024**3 * 0.95
        video_stream = next((s for s in self.probe_data["streams"] if s["codec_type"] == "video"), None)
        if not video_stream:
            raise ValueError("No video stream found")

        # Calculate resolution multiplier
        height = int(video_stream.get("height", 0))
        frame_rate = eval(str(video_stream.get("r_frame_rate", "24/1")))
        resolution_multiplier = {2160: 1.0, 1440: 0.7, 1080: 0.5}.get(height, 0.3)
        if frame_rate > 30:
            resolution_multiplier *= 1.5

        # Calculate audio bits
        audio_streams = sum(1 for s in self.probe_data["streams"] if s["codec_type"] == "audio")
        audio_bitrate = int(self.config.audio_bitrate.rstrip("k")) * 1000
        total_audio_bits = audio_streams * audio_bitrate * self.duration if self.config.copy_audio else 0

        # Calculate target video bitrate
        target_bitrate = int((total_bits - total_audio_bits) / self.duration * resolution_multiplier)
        target_bitrate = max(self.config.min_video_bitrate, min(target_bitrate, self.config.max_video_bitrate))
        target_bitrate = (target_bitrate // 1_000_000) * 1_000_000

        logger.info(f"Target video bitrate: {target_bitrate/1_000_000:.2f} Mbps")
        return target_bitrate

    def _build_command(self, output_path: Path, target_bitrate: int) -> List[str]:
        if self.hw_support is None:
            self.hw_support = bool(
                subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True).stdout.find(
                    self.config.hardware_encoder
                )
                != -1
            )

        use_hw = self.config.use_hardware_acceleration and self.hw_support
        stream_indexes = self._get_stream_indexes()
        video_stream = next((s for s in self.probe_data["streams"] if s["codec_type"] == "video"), None)  # type: ignore
        if not video_stream:
            raise ValueError("No video stream found")

        cmd = ["ffmpeg", "-y", "-hwaccel", "videotoolbox", "-i", str(self.input_file)]

        # Map streams
        cmd.extend(["-map", f"0:{stream_indexes['video'][0]}"])
        if self.config.copy_audio:
            for idx in stream_indexes["audio"]:
                cmd.extend(["-map", f"0:{idx}"])
        if self.config.copy_subtitles:
            for idx in stream_indexes["subtitle"]:
                cmd.extend(["-map", f"0:{idx}"])

        # Video encoding settings
        if use_hw:
            cmd.extend(
                [
                    "-c:v",
                    self.config.hardware_encoder,
                    "-b:v",
                    str(target_bitrate),
                    "-maxrate",
                    str(int(target_bitrate * 1.5)),
                    "-bufsize",
                    str(int(target_bitrate * 2)),
                    "-tag:v",
                    "hvc1",
                    "-allow_sw",
                    "1" if self.config.allow_sw_fallback else "0",
                    "-pix_fmt",
                    "p010le",
                    "-profile:v",
                    "main10",
                    "-quality",
                    self.config.quality_preset,
                    "-colorspace",
                    video_stream.get("color_space", "bt2020nc"),
                    "-color_primaries",
                    video_stream.get("color_primaries", "bt2020"),
                    "-color_trc",
                    video_stream.get("color_transfer", "smpte2084"),
                    "-alpha_quality",
                    "0.9",
                    "-field_order",
                    "progressive",
                    "-probesize",
                    "50000000",
                    "-g",
                    "48",
                    "-realtime",
                    self.config.realtime,
                    "-bf",
                    self.config.b_frames,
                ]
            )
        else:
            x265_params = [
                f"bitrate={target_bitrate//1000}",
                "hdr10=1",
                f"colorprim={video_stream.get('color_primaries', 'bt2020')}",
                f"transfer={video_stream.get('color_transfer', 'smpte2084')}",
                f"colormatrix={video_stream.get('color_space', 'bt2020nc')}",
                "repeat-headers=1",
                f"max-cll={self.config.hdr_params['max_cll']}",
                f"master-display={self.config.hdr_params['master_display']}",
            ]
            cmd.extend(
                [
                    "-c:v",
                    self.config.fallback_encoder,
                    "-preset",
                    self.config.preset.value,
                    "-x265-params",
                    ":".join(x265_params),
                    "-profile:v",
                    "main10",
                    "-pix_fmt",
                    "yuv420p10le",
                ]
            )

        # Audio and subtitle settings
        if self.config.copy_audio:
            cmd.extend(
                [
                    "-c:a",
                    "copy",
                    "-b:a",
                    self.config.audio_bitrate,
                    "-metadata:s:a",
                    "spatial_audio=1",
                ]
            )
        else:
            cmd.extend(
                [
                    "-c:a",
                    self.config.audio_codec,
                    "-b:a",
                    self.config.audio_bitrate,
                    "-metadata:s:a",
                    "spatial_audio=1",
                ]
            )

        if self.config.copy_subtitles:
            cmd.extend(["-c:s", "copy"])

        # Output settings
        cmd.extend(["-map_metadata", "0", "-map_chapters", "0", "-max_muxing_queue_size", "4096", str(output_path)])
        return cmd

    def encode(self, output_path: Union[str, Path]) -> None:  # noqa: C901
        output_path = Path(output_path)
        if output_path.exists() and output_path.stat().st_size > 0:
            raise FileExistsError(f"Output file exists: {output_path}")

        try:
            if not self.probe_data:
                self.probe_file()

            target_bitrate = self._calculate_bitrate()
            cmd = self._build_command(output_path, target_bitrate)
            logger.info("Starting encoding...")

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

            if process.stderr is None:
                raise EncodingError("Failed to open stderr pipe")

            last_progress = time.time()
            progress_pattern = re.compile(r"frame=\s*(\d+)")

            while True:
                line = process.stderr.readline()
                if not line and process.poll() is not None:
                    break

                if line:
                    if "frame=" in line:
                        last_progress = time.time()
                        if match := progress_pattern.search(line):
                            logger.info(f"Frame: {match.group(1)}")
                    elif "error" in line.lower():
                        logger.error(line.strip())

                if time.time() - last_progress > 30:
                    process.terminate()
                    raise EncodingError("Encoding stalled")

            if process.returncode != 0:
                raise EncodingError(f"FFmpeg failed with code {process.returncode}")

            if output_path.exists():
                final_size = output_path.stat().st_size / 1024**3
                logger.info(f"Completed. Output size: {final_size:.2f}GB")
                subprocess.run(["ffprobe", str(output_path)], check=True, capture_output=True)
            else:
                raise EncodingError("Output file not created")

        except Exception as e:
            logger.error(f"Encoding failed: {e!s}")
            if output_path.exists():
                output_path.unlink()
            raise


def main() -> None:  # noqa: C901
    start_time = time.time()
    try:
        logger.info("=== Starting Video Processing ===")

        # Create optimized configuration
        config = EncodingConfig(
            target_size_gb=6.0,
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
            verify_cmd = ["ffprobe", "-v", "error", "-i", str(output_file), "-f", "null", "-"]
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
