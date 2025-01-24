# custom_logger.py
import logging
import subprocess
import time
import sys
from datetime import datetime
from typing import Any, override
from contextlib import suppress
from pathlib import Path
from utils import ProbeData, StreamDict


class CustomLogger(logging.Logger):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.setLevel(logging.INFO)
        self._setup_handlers()
        self.last_flush: float = time.time()
        self.flush_interval: int = 30  # 30 seconds default flush interval
        self._max_log_size: int = 10 * 1024 * 1024  # 10MB default, hidden implementation detail
        self.log_file: str = ""  # Initialize log_file
        self.last_frame_log_time: float = 0.0  # Initialize last_frame_log_time

    def _setup_handlers(self) -> None:
        """Setup handlers maintaining original behavior but with internal improvements"""
        # Stream handler setup (exactly as original)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        self.addHandler(stream_handler)

        # File handler setup (maintaining original filename format)
        self.log_file = f"encoding_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        self.addHandler(file_handler)

    def should_flush(self) -> bool:
        """Internal method for flush control"""
        current_time = time.time()
        if (current_time - self.last_flush) >= self.flush_interval:
            self.last_flush = current_time
            return True
        return False

    def flush_handlers(self) -> None:
        """Internal method for controlled flushing"""
        for handler in self.handlers:
            with suppress(OSError):
                handler.flush()

    @override
    def info(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Maintains original interface but with controlled flushing"""
        super().info(msg, *args, **kwargs)
        if self.should_flush():
            self.flush_handlers()

    @override
    def warning(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Maintains original interface but with immediate flush"""
        super().warning(msg, *args, **kwargs)
        self.flush_handlers()  # Always flush warnings

    @override
    def error(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Maintains original interface but with immediate flush"""
        super().error(msg, *args, **kwargs)
        self.flush_handlers()  # Always flush errors

    def log_input_analysis(self, probe_data: ProbeData) -> None:
        """Maintains exact original interface and output format"""
        streams: list[StreamDict] = probe_data.get("streams", [])
        if not streams:
            self.error("Invalid probe data format")
            return

        video_stream = next((s for s in probe_data["streams"] if s.get("codec_type") == "video"), None)
        if video_stream:
            self.info("Video Stream Information:")
            self.info(f"Codec: {video_stream.get('codec_name', 'unknown')}")
            self.info(f"Resolution: {video_stream.get('width', '?')}x{video_stream.get('height', '?')}")
            self.info(f"Pixel Format: {video_stream.get('pix_fmt', 'unknown')}")
            self.info(f"Color Space: {video_stream.get('color_space', 'unknown')}")
            self.info(f"Color Transfer: {video_stream.get('color_transfer', 'unknown')}")
            self.info(f"Frame Rate: {video_stream.get('r_frame_rate', 'unknown')}")
            self.info(f"Bit Depth: {video_stream.get('bits_per_raw_sample', 'unknown')}")

        audio_streams = [s for s in probe_data["streams"] if s.get("codec_type") == "audio"]
        self.info(f"\nFound {len(audio_streams)} audio stream(s):")
        for idx, stream in enumerate(audio_streams):
            language = stream.get("tags", {}).get("language", "unknown")
            codec = stream.get("codec_name", "unknown")
            channels = stream.get("channels", "unknown")
            self.info(f"Audio Stream {idx + 1}: {codec}, {channels} channels, Language: {language}")

        subtitle_streams = [s for s in probe_data["streams"] if s.get("codec_type") == "subtitle"]
        self.info(f"\nFound {len(subtitle_streams)} subtitle stream(s):")
        for idx, stream in enumerate(subtitle_streams):
            language = stream.get("tags", {}).get("language", "unknown")
            codec = stream.get("codec_name", "unknown")
            self.info(f"Subtitle Stream {idx + 1}: {codec}, Language: {language}")

    def log_encoding_start(self, output_file: Path, target_bitrate: float, cmd: list[str]) -> None:
        """Maintains exact original interface"""
        self.info("\n=== Starting Encoding Process ===")
        self.info(f"Output File: {output_file}")
        self.info(f"Target Bitrate: {target_bitrate / 1_000_000:.2f} Mbps")
        self.info("FFmpeg Command:")
        self.info(" ".join(str(c) for c in cmd))

    def log_encoding_complete(self, input_file: Path, output_file: Path, encoding_duration: float) -> None:
        """Maintains exact original interface with improved error handling"""
        try:
            input_size = input_file.stat().st_size / (1024 * 1024 * 1024)  # GB
            output_size = output_file.stat().st_size / (1024 * 1024 * 1024)  # GB
            compression_ratio = input_size / output_size if output_size > 0 else 0

            self.info("\n=== Encoding Complete ===")
            self.info(f"Input Size: {input_size:.2f} GB")
            self.info(f"Output Size: {output_size:.2f} GB")
            self.info(f"Compression Ratio: {compression_ratio:.2f}:1")
            self.info(f"Encoding Duration: {encoding_duration / 3600:.2f} hours")
            self.info(f"Average Processing Speed: {(input_size * 1024) / (encoding_duration / 60):.2f} MB/minute")
        except (OSError, ZeroDivisionError) as e:
            self.error(f"Error calculating file statistics: {e!s}")

    def log_verification(self, output_file: Path) -> None:
        """Maintains original interface with improved subprocess handling"""
        verify_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-i",
            str(output_file),
            "-show_streams",
            "-show_format",
        ]

        try:
            # Use subprocess with timeout and proper cleanup
            process = subprocess.Popen(verify_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            try:
                _stdout, stderr = process.communicate(timeout=300)  # 5-minute timeout

                if process.returncode != 0:
                    self.error("Output file verification: FAILED")
                    self.error(f"Return code: {process.returncode}")
                    if stderr:
                        self.error(stderr.strip())
                elif stderr:
                    self.warning("Output file verification: WARNING")
                    self.warning(stderr.strip())
                else:
                    self.info("Output file verification: PASSED")

            except subprocess.TimeoutExpired:
                process.kill()
                _stdout, stderr = process.communicate()
                self.error("Verification process timed out")

        except Exception as e:
            self.error(f"Verification error: {e!s}")

    def log_final_stats(self, start_time: float) -> None:
        """Maintains exact original interface"""
        total_duration = time.time() - start_time
        self.info(f"\nTotal Processing Time: {total_duration / 3600:.2f} hours")
        self.info("=== Processing Completed Successfully ===")

    def log_estimated_duration(self, duration: float) -> None:
        total_frames_guess: int = int(duration * 24)
        avg_time_per_frame: float = (
            0.018  # This is a rough estimate and may vary based on the specifics of the default encoding process
        )
        estimated_time_in_seconds: float = total_frames_guess * avg_time_per_frame
        estimated_time_in_mins: float = estimated_time_in_seconds / 60
        self.info(f"Estimated time for encoding: {estimated_time_in_mins:.2f} minutes")

    def __del__(self) -> None:
        """Clean up resources on deletion"""
        for handler in self.handlers:
            with suppress(Exception):
                handler.close()
