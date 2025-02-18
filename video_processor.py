# video_processor.py
import subprocess
import json
import shutil
import re
import time
from pathlib import Path
from subprocess import Popen
from typing import cast, Any

from custom_logger import CustomLogger as Logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from utils import ProbeError, ProbeData, EncodingConfig, EncodingError, StreamDict
from ffmpeg_configs import dolby_vision_metadata, hevc_metadata

# Create a custom logger
logger = Logger(__name__)


class VideoProcessor:
    """
    A class responsible for processing video files.

    Attributes:
        input_file (Path): The input video file.
        config (EncodingConfig): The encoding configuration.
        probe_data (ProbeData): The probe data of the input file.
        input_size_gb (float): The size of the input file in GB.
        duration (float): The duration of the input file in seconds.
        hw_support (bool): Whether hardware acceleration is supported.
    """

    def __init__(self, input_file: str | Path, config: EncodingConfig | None = None):
        """
        Initializes the VideoProcessor instance.

        Args:
            input_file (str | Path): The input video file.
            config (EncodingConfig | None): The encoding configuration. Defaults to None.
        """
        self.input_file: Path = Path(input_file)
        self.config: EncodingConfig = config or EncodingConfig()
        if not self.input_file.exists() or not self.input_file.is_file():
            raise FileNotFoundError(f"Invalid input file: {self.input_file}")
        if not all(shutil.which(tool) for tool in ["ffmpeg", "ffprobe"]):
            raise OSError("ffmpeg or ffprobe not found in PATH")
        self.probe_data: ProbeData | None = None
        self.input_size_gb: float = 0.0
        self.duration: float = 0.0
        self.hw_support: bool | None = None
        self.has_dolby_vision: bool = False
        self.dv_profile: int | None = None
        self.dv_bl_present_flag: int | None = None
        self.dv_el_present_flag: int | None = None
        self.dv_bl_signal_compatibility_id: int | None = None
        self.video_metadata: dict[str, Any] = {}

    @retry(
        retry=retry_if_exception_type((subprocess.CalledProcessError, json.JSONDecodeError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        before_sleep=lambda retry_state: logger.warning(f"Retrying probe_file attempt {retry_state.attempt_number}"),
    )
    def probe_file(self) -> ProbeData:
        """
        Probes the input file using ffprobe and returns the probe data.
        Detects HDR, Dolby Vision, and advanced video metadata.

        Returns:
            ProbeData: The probe data of the input file.
        Raises:
            ProbeError: If the probe fails.
        """
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                "-show_frames",
                "-read_intervals",
                "%+#1",  # Read first frame for detailed metadata
                str(self.input_file),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            probe_data = json.loads(result.stdout)

            # Ensure the loaded data matches our expected type
            self.probe_data = cast("ProbeData", probe_data)
            format_info = self.probe_data["format"]

            # Basic file info
            self.input_size_gb = float(format_info["size"]) / (1024**3)
            self.duration = float(format_info["duration"])

            # Get video stream
            video_stream = next((s for s in self.probe_data["streams"] if s["codec_type"] == "video"), None)
            if video_stream:
                # Detect HDR/DoVi features
                self.video_metadata = {
                    "codec_name": video_stream.get("codec_name", ""),
                    "height": int(video_stream.get("height", 0)),
                    "width": int(video_stream.get("width", 0)),
                    "frame_rate": eval(str(video_stream.get("r_frame_rate", "24/1"))),
                    "is_hdr10": video_stream.get("color_transfer") == "smpte2084",
                    "is_hlg": video_stream.get("color_transfer") == "arib-std-b67",
                    "has_dovi": any("dovi_configuration_record" in str(s) for s in self.probe_data["streams"]),
                    "color_space": video_stream.get("color_space", ""),
                    "color_transfer": video_stream.get("color_transfer", ""),
                    "color_primaries": video_stream.get("color_primaries", ""),
                    "bits_per_raw_sample": int(video_stream.get("bits_per_raw_sample", 8)),  # type: ignore
                    "profile": video_stream.get("profile", ""),
                }

                # Detect DoVi profile if present
                if self.video_metadata["has_dovi"]:
                    side_data = video_stream.get("side_data_list", [])
                    for data in side_data:  # type: ignore
                        if "dovi_configuration_record" in str(data):
                            self.video_metadata["dovi_profile"] = data.get("dovi_profile", 0)
                            self.video_metadata["dovi_bl_present_flag"] = data.get("dovi_bl_present_flag", 1)
                            self.video_metadata["dovi_el_present_flag"] = data.get("dovi_el_present_flag", 0)
                            break

                logger.info(f"Input: {self.input_size_gb:.2f}GB, Duration: {self.duration:.2f}s")
                logger.info(
                    f"Video: {self.video_metadata['width']}x{self.video_metadata['height']}, "
                    f"{'HDR10' if self.video_metadata['is_hdr10'] else ''} "
                    f"{'Dolby Vision' if self.video_metadata['has_dovi'] else ''}",
                )

            return self.probe_data

        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            raise ProbeError(f"Probe failed: {e!s}") from e

    def _get_stream_indexes(self) -> dict[str, list[int]]:
        if not self.probe_data:
            self.probe_file()

        if not self.probe_data:  # This check is for type checker
            raise ValueError("Probe data is still None after probe_file()")

        indexes: dict[str, list[int]] = {"video": [], "audio": [], "subtitle": []}
        for stream in self.probe_data["streams"]:
            stream_type = stream.get("codec_type", "")
            if stream_type not in indexes:
                continue

            if (self.config.english_audio_only and stream_type == "audio") or (
                self.config.english_subtitles_only and stream_type == "subtitle"
            ):
                tags = stream.get("tags", {})
                if tags.get("language", "").lower() in {"eng", "english"}:
                    indexes[stream_type].append(stream["index"])
            else:
                indexes[stream_type].append(stream["index"])

        return indexes

    def _check_dolby_vision(self) -> None:
        """
        Check if the input file has Dolby Vision metadata and set relevant attributes.
        """
        if not self.probe_data:
            self.probe_file()

        if self.probe_data is None or "streams" not in self.probe_data:
            return  # No streams found, so no Dolby Vision metadata

        video_stream = next((s for s in self.probe_data["streams"] if s.get("codec_type") == "video"), None)
        if video_stream is None:
            return  # No video stream found, so no Dolby Vision metadata

        # Check for Dolby Vision side data
        side_data = cast(list[dict[str, Any]], video_stream.get("side_data_list", []))
        dovi_conf: dict[str, Any] | None = next(
            (sd for sd in side_data if sd.get("side_data_type") == "DOVI configuration record"),
            None,
        )

        if dovi_conf:
            self.has_dolby_vision = True
            self.dv_profile = int(dovi_conf.get("dv_profile", 0))
            self.dv_bl_present_flag = int(dovi_conf.get("dv_bl_present_flag", 0))
            self.dv_el_present_flag = int(dovi_conf.get("dv_el_present_flag", 0))
            self.dv_bl_signal_compatibility_id = int(dovi_conf.get("dv_bl_signal_compatibility_id", 0))
            logger.info(f"Detected Dolby Vision Profile {self.dv_profile}")
        else:
            logger.info("No Dolby Vision metadata detected")

    def calculate_bitrate(self) -> int:
        """Public method to calculate bitrate."""
        return self._calculate_bitrate()

    def build_command(self, output_path: Path, target_bitrate: int) -> list[str]:
        """Public method to build command."""
        return self._build_command(output_path, target_bitrate)

    def _calculate_bitrate(self) -> int:
        """
        Calculates target bitrate with enhanced HDR/DoVi handling.
        """
        dovi_profile_high_complexity = 7

        # Frame Rate Thresholds
        high_framerate_threshold = 30

        # Bit Depth Constants
        standard_bit_depth = 8

        # Bitrate Multipliers
        dovi_profile_high_multiplier = 1.3
        dovi_profile_default_multiplier = 1.2
        hdr_10_bitrate_multiplier = 1.15
        hlg_bitrate_multiplier = 1.1
        high_framerate_multiplier = 1.5
        high_bit_depth_multiplier = 1.1
        hevc_efficiency_multiplier = 0.7

        if not self.probe_data or self.duration <= 0:
            raise ValueError("Invalid probe data")

        # Calculate total bits with 5% buffer for container overhead
        total_bits = self.config.target_size_gb * 8 * 1024**3 * 0.95

        # Get video metadata from probe
        vm = self.video_metadata  # shorthand reference

        # Base resolution multiplier (adjusted for content type)
        resolution_multiplier = {
            2160: 1.0,
            1440: 0.75,
            1080: 0.55,
        }.get(vm["height"], 0.35)

        # HDR/DoVi content type multiplier
        content_type_multiplier = 1.0
        if vm["has_dovi"]:
            # DoVi needs more bitrate, especially for profile 7
            dovi_profile = vm.get("dovi_profile", 5)
            content_type_multiplier = (
                dovi_profile_high_multiplier
                if dovi_profile == dovi_profile_high_complexity
                else dovi_profile_default_multiplier
            )
        elif vm["is_hdr10"]:
            content_type_multiplier = hdr_10_bitrate_multiplier  # HDR10 needs slightly more than SDR
        elif vm["is_hlg"]:
            content_type_multiplier = hlg_bitrate_multiplier  # HLG needs slightly more than SDR

        # Frame rate handling
        frame_rate = vm["frame_rate"]
        if frame_rate > high_framerate_threshold:
            content_type_multiplier *= high_framerate_multiplier  # Higher bitrate for high frame rate

        # Bit depth multiplier
        bit_depth = vm["bits_per_raw_sample"]
        bit_depth_multiplier = (
            1.0 if bit_depth <= standard_bit_depth else high_bit_depth_multiplier
        )  # 10-bit needs more bitrate

        # Codec efficiency
        codec_name = vm["codec_name"]
        codec_multiplier = hevc_efficiency_multiplier if codec_name == "hevc" else 1.0  # HEVC is more efficient

        # Calculate audio bitrate requirements
        audio_streams = sum(1 for s in self.probe_data["streams"] if s["codec_type"] == "audio")
        audio_bitrate = int(self.config.audio_bitrate.rstrip("k")) * 1000
        total_audio_bits = audio_streams * audio_bitrate * self.duration if self.config.copy_audio else 0

        # Apply all multipliers to calculate target video bitrate
        target_video_bits = (
            (total_bits - total_audio_bits)
            * resolution_multiplier
            * content_type_multiplier
            * bit_depth_multiplier
            * codec_multiplier
        )

        target_bitrate = int(target_video_bits / self.duration)

        # Set minimum bitrates based on content type
        min_bitrate = self.config.min_video_bitrate
        if vm["has_dovi"]:
            min_bitrate = max(12_000_000, min_bitrate)  # Minimum 12 Mbps for DoVi
        elif vm["is_hdr10"]:
            min_bitrate = max(8_000_000, min_bitrate)  # Minimum 8 Mbps for HDR10

        # Apply min and max constraints and normalize to nearest million
        target_bitrate = max(min_bitrate, min(target_bitrate, self.config.max_video_bitrate))
        target_bitrate = (target_bitrate // 1_000_000) * 1_000_000

        # Logging
        logger.info("Content type multipliers:")
        logger.info(f"Resolution: {resolution_multiplier:.2f}")
        logger.info(f"HDR/DoVi: {content_type_multiplier:.2f}")
        logger.info(f"Bit depth: {bit_depth_multiplier:.2f}")
        logger.info(f"Codec: {codec_multiplier:.2f}")
        logger.info(f"Target video bitrate: {target_bitrate / 1_000_000:.2f} Mbps")

        return target_bitrate

    def _build_command(self, output_path: Path, target_bitrate: int) -> list[str]:
        """Build FFmpeg command with the given parameters.

        Args:
            output_path: Path to the output file
            target_bitrate: Target bitrate for the video

        Returns:
            list[str]: FFmpeg command as a list of strings
        """
        self._check_dolby_vision()
        self._check_hardware_support()

        video_stream = self._get_video_stream()
        stream_indexes = self._get_stream_indexes()
        use_hw = False
        if self.config.use_hardware_acceleration and self.hw_support is not None:
            use_hw = self.hw_support

        cmd = self._build_base_command(stream_indexes)
        cmd.extend(self._build_video_encoding_settings(use_hw, target_bitrate, video_stream))
        cmd.extend(self._build_audio_subtitle_settings())

        if use_hw and self.has_dolby_vision:  # hdr metadata
            cmd.extend(dolby_vision_metadata)
            cmd.extend(
                [
                    str(output_path),
                ],
            )
            return cmd

        # Output settings
        cmd.extend(hevc_metadata)
        cmd.extend(
            [
                str(output_path),
            ],
        )
        return cmd

    def _check_hardware_support(self) -> None:
        """Check if hardware encoding is supported."""
        if self.hw_support is None:
            ffmpeg_output = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True, check=False).stdout
            self.hw_support = self.config.hardware_encoder in ffmpeg_output

    def _get_video_stream(self) -> StreamDict:
        """Get the video stream information.

        Returns:
            StreamDict: Video stream information with required and optional fields

        Raises:
            ValueError: If no video stream is found or probe data is not available
        """
        if self.probe_data is not None:
            video_stream = next((s for s in self.probe_data["streams"] if s["codec_type"] == "video"), None)
            if not video_stream:
                raise ValueError("No video stream found")
            return video_stream
        raise ValueError("Probe data is not available")

    def _build_base_command(self, stream_indexes: dict[str, list[int]]) -> list[str]:
        """Build the base FFmpeg command with input and stream mapping."""
        cmd: list[str] = ["ffmpeg", "-y", "-hwaccel", "videotoolbox", "-i", str(self.input_file)]

        # Map streams
        cmd.extend(["-map", f"0:{stream_indexes['video'][0]}"])

        if self.config.copy_audio:
            for idx in stream_indexes["audio"]:
                cmd.extend(["-map", f"0:{idx}"])

        if self.config.copy_subtitles:
            for idx in stream_indexes["subtitle"]:
                cmd.extend(["-map", f"0:{idx}"])

        return cmd

    def _build_dolby_vision_settings(self, target_bitrate: int) -> list[str]:
        """Build Dolby Vision specific encoding settings."""
        return [
            "-c:v",
            self.config.hardware_encoder,
            "-allow_sw",
            "1" if self.config.allow_sw_fallback else "0",
            "-profile:v",
            "main10",
            "-b:v",
            str(target_bitrate),
            "-maxrate",
            str(int(target_bitrate * 1.5)),
            "-bufsize",
            str(int(target_bitrate * 2)),
            "-map_metadata:s:v:0",
            "0:s:v:0",
            "-strict",
            "-1",
            "-copy_unknown",
            "-metadata:s:v:0",
            f"dv_profile={self.dv_profile}",
            "-metadata:s:v:0",
            f"dv_bl_present_flag={self.dv_bl_present_flag}",
            "-metadata:s:v:0",
            f"dv_el_present_flag={self.dv_el_present_flag}",
            "-metadata:s:v:0",
            f"dv_bl_signal_compatibility_id={self.dv_bl_signal_compatibility_id}",
            "-max_ref_frames",
            self.config.max_ref_frames,
            "-quality",
            self.config.quality_preset.value,
            "-field_order",
            "progressive",
            "-probesize",
            "50000000",
            "-realtime",
            self.config.realtime,
            "-bf",
            self.config.b_frames,
            "-g",
            self.config.group_of_pictures,
            "-tag:v",
            "hvc1",
        ]

    def _build_hardware_encoding_settings(self, target_bitrate: int, video_stream: StreamDict) -> list[str]:
        """Build hardware encoding specific settings."""
        return [
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
            "-profile:v",
            "main10",
            "-quality",
            self.config.quality_preset.value,
            "-colorspace",
            video_stream.get("color_space", "bt2020nc"),
            "-field_order",
            "progressive",
            "-probesize",
            "50000000",
            "-max_ref_frames",
            self.config.max_ref_frames,
            "-g",
            self.config.group_of_pictures,
            "-realtime",
            self.config.realtime,
            "-bf",
            self.config.b_frames,
        ]

    def _build_software_encoding_settings(self, target_bitrate: int, video_stream: StreamDict) -> list[str]:
        """Build software encoding specific settings."""
        x265_params = [
            f"bitrate={target_bitrate // 1000}",
            "hdr10=1",
            f"colorprim={video_stream.get('color_primaries', 'bt2020')}",
            f"transfer={video_stream.get('color_transfer', 'smpte2084')}",
            f"colormatrix={video_stream.get('color_space', 'bt2020nc')}",
            "repeat-headers=1",
            f"max-cll={self.config.hdr_params['max_cll']}",
            f"master-display={self.config.hdr_params['master_display']}",
        ]

        return [
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

    def _build_video_encoding_settings(self, use_hw: bool, target_bitrate: int, video_stream: StreamDict) -> list[str]:
        """Build video encoding settings based on hardware support and Dolby Vision."""
        if use_hw and self.has_dolby_vision:
            logger.info("Using hardware encoding with Dolby Vision!!!")
            return self._build_dolby_vision_settings(target_bitrate)
        if use_hw:
            return self._build_hardware_encoding_settings(target_bitrate, video_stream)
        return self._build_software_encoding_settings(target_bitrate, video_stream)

    def _build_audio_subtitle_settings(self) -> list[str]:
        """Build audio and subtitle encoding settings."""
        cmd: list[str] = []

        if self.config.copy_audio:
            cmd.extend(
                [
                    "-c:a",
                    "copy",
                    "-b:a",
                    self.config.audio_bitrate,
                ],
            )
        else:
            cmd.extend(
                [
                    "-c:a",
                    self.config.audio_codec,
                    "-b:a",
                    self.config.audio_bitrate,
                ],
            )

        if self.config.copy_subtitles:
            cmd.extend(["-c:s", "copy"])

        return cmd

    def _validate_output_path(self, output_path: str | Path) -> Path:
        """
        Validate the output path and ensure it doesn't already exist with content.
        """
        output_path = Path(output_path)
        if output_path.exists() and output_path.stat().st_size > 0:
            raise FileExistsError(f"Output file exists: {output_path}")
        return output_path

    def _monitor_encoding_process(self, process: Popen[str], encoding_timeout_seconds: int) -> None:
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
                        frame_number = match.group(1)
                        logger.info(f"Processed frame: {frame_number}")
                elif "error" in line.lower():
                    logger.error(line.strip())

            if time.time() - last_progress > encoding_timeout_seconds:
                process.terminate()
                raise EncodingError("Encoding stalled")

    def _verify_output(self, output_path: Path, process: Popen[str]) -> None:
        if process.returncode != 0:
            raise EncodingError(f"FFmpeg failed with code {process.returncode}")

        if output_path.exists():
            final_size = output_path.stat().st_size / 1024**3
            logger.info(f"Completed. Output size: {final_size:.2f}GB")
            subprocess.run(["ffprobe", str(output_path)], check=True, capture_output=True)
        else:
            raise EncodingError("Output file not created")

    @retry(
        retry=retry_if_exception_type(EncodingError),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        before_sleep=lambda retry_state: logger.warning(f"Retrying encoding attempt {retry_state.attempt_number}"),
    )
    def encode(self, output_path: str | Path) -> None:
        """
        Encode the input file to the specified output path.

        Args:
            output_path (Union[str, Path]): The path to the output file.

        Raises:
            FileExistsError: If the output file already exists.
            EncodingError: If the encoding process fails.
        """
        encoding_timeout_seconds = 30

        try:
            output_path = self._validate_output_path(output_path)

            if not self.probe_data:
                self.probe_file()

            target_bitrate = self._calculate_bitrate()
            cmd = self._build_command(output_path, target_bitrate)

            logger.info("Starting encoding...")
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            self._monitor_encoding_process(process, encoding_timeout_seconds)
            self._verify_output(output_path, process)

        except Exception as e:
            logger.error(f"Encoding failed: {e!s}")
            output_path_obj = Path(output_path)  # Convert to Path to handle Union type
            if output_path_obj.exists():
                output_path_obj.unlink()
            raise


if __name__ == "__main__":
    pass
