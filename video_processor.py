# video_processor.py
import subprocess
import json
import shutil
import re
import time
from pathlib import Path
from typing import Optional, Union, Dict, List, cast

from custom_logger import CustomLogger as Logger
from utils import ProbeError, ProbeData, EncodingConfig, EncodingError

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

    def __init__(self, input_file: Union[str, Path], config: Optional[EncodingConfig] = None):
        """
        Initializes the VideoProcessor instance.

        Args:
            input_file (Union[str, Path]): The input video file.
            config (Optional[EncodingConfig]): The encoding configuration. Defaults to None.
        """
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
        self.has_dolby_vision: bool = False
        self.dv_profile: Optional[int] = None
        self.dv_bl_present_flag: Optional[int] = None
        self.dv_el_present_flag: Optional[int] = None
        self.dv_bl_signal_compatibility_id: Optional[int] = None

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
            self.probe_data = cast(ProbeData, probe_data)
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
                    f"{'HDR10' if self.video_metadata['is_hdr10'] else ''}"
                    f"{'Dolby Vision' if self.video_metadata['has_dovi'] else ''}"
                )

            return self.probe_data

        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            raise ProbeError(f"Probe failed: {e!s}") from e

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
        side_data = video_stream.get("side_data_list", [])
        if isinstance(side_data, list):
            dovi_conf = next((sd for sd in side_data if sd.get("side_data_type") == "DOVI configuration record"), None)
        else:
            dovi_conf = None

        if dovi_conf:
            self.has_dolby_vision = True
            self.dv_profile = int(dovi_conf.get("dv_profile", 0))
            self.dv_bl_present_flag = int(dovi_conf.get("dv_bl_present_flag", 0))
            self.dv_el_present_flag = int(dovi_conf.get("dv_el_present_flag", 0))
            self.dv_bl_signal_compatibility_id = int(dovi_conf.get("dv_bl_signal_compatibility_id", 0))
            logger.info(f"Detected Dolby Vision Profile {self.dv_profile}")
        else:
            logger.info("No Dolby Vision metadata detected")

    def _calculate_bitrate(self) -> int:
        """
        Calculates target bitrate with enhanced HDR/DoVi handling.
        """
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
            content_type_multiplier = 1.3 if dovi_profile == 7 else 1.2
        elif vm["is_hdr10"]:
            content_type_multiplier = 1.15  # HDR10 needs slightly more than SDR
        elif vm["is_hlg"]:
            content_type_multiplier = 1.1  # HLG needs slightly more than SDR

        # Frame rate handling
        frame_rate = vm["frame_rate"]
        if frame_rate > 30:
            content_type_multiplier *= 1.5  # Higher bitrate for high frame rate

        # Bit depth multiplier
        bit_depth = vm["bits_per_raw_sample"]
        bit_depth_multiplier = 1.0 if bit_depth <= 8 else 1.1  # 10-bit needs more bitrate

        # Codec efficiency
        codec_name = vm["codec_name"]
        codec_multiplier = 0.7 if codec_name == "hevc" else 1.0  # HEVC is more efficient

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

    def _build_command(self, output_path: Path, target_bitrate: int) -> List[str]:
        self._check_dolby_vision()

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

        if use_hw and self.has_dolby_vision:
            logger.info("Using hardware encoding with Dolby Vision!!!")
            cmd.extend(
                [
                    # Encoder settings
                    "-c:v",
                    self.config.hardware_encoder,
                    "-allow_sw",
                    "1" if self.config.allow_sw_fallback else "0",
                    # Video format settings
                    "-pix_fmt",
                    "p010le",
                    "-profile:v",
                    "main10",
                    # Bitrate controls
                    "-b:v",
                    str(target_bitrate),
                    "-maxrate",
                    str(int(target_bitrate * 1.5)),
                    "-bufsize",
                    str(int(target_bitrate * 2)),
                    # Dolby Vision mapping
                    "-map_metadata:s:v:0",
                    "0:s:v:0",
                    "-strict",
                    "-1",
                    "-copy_unknown",
                    # Dolby Vision metadata
                    "-metadata:s:v:0",
                    f"dv_profile={self.dv_profile}",
                    "-metadata:s:v:0",
                    f"dv_bl_present_flag={self.dv_bl_present_flag}",
                    "-metadata:s:v:0",
                    f"dv_el_present_flag={self.dv_el_present_flag}",
                    "-metadata:s:v:0",
                    f"dv_bl_signal_compatibility_id={self.dv_bl_signal_compatibility_id}",
                    # Encoding settings
                    "-quality",
                    self.config.quality_preset,
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
                    # Container tag
                    "-tag:v",
                    "dvh1",  # Dolby Vision tag
                ]
            )

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

    def encode(self, output_path: Union[str, Path]) -> None:
        """
        Encode the input file to the specified output path.
        Args:
            output_path (Union[str, Path]): The path to the output file.

        Raises:
            FileExistsError: If the output file already exists.
            EncodingError: If the encoding process fails.
        """
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


if __name__ == "__main__":
    pass
