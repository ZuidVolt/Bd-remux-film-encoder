import logging
import subprocess
import time


class CustomLogger(logging.Logger):
    def __init__(self, name):
        super().__init__(name)
        self.setLevel(logging.INFO)
        self.handler = logging.StreamHandler()
        self.handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        self.addHandler(self.handler)

    def log_input_analysis(self, probe_data):
        video_stream = next((s for s in probe_data["streams"] if s["codec_type"] == "video"), None)
        if video_stream:
            self.info("Video Stream Information:")
            self.info(f"Codec: {video_stream.get('codec_name', 'unknown')}")
            self.info(f"Resolution: {video_stream.get('width', '?')}x{video_stream.get('height', '?')}")
            self.info(f"Pixel Format: {video_stream.get('pix_fmt', 'unknown')}")
            self.info(f"Color Space: {video_stream.get('color_space', 'unknown')}")
            self.info(f"Color Transfer: {video_stream.get('color_transfer', 'unknown')}")
            self.info(f"Frame Rate: {video_stream.get('r_frame_rate', 'unknown')}")
            self.info(f"Bit Depth: {video_stream.get('bits_per_raw_sample', 'unknown')}")

        audio_streams = [s for s in probe_data["streams"] if s["codec_type"] == "audio"]
        self.info(f"\nFound {len(audio_streams)} audio stream(s):")
        for idx, stream in enumerate(audio_streams):
            language = stream.get("tags", {}).get("language", "unknown")
            codec = stream.get("codec_name", "unknown")
            channels = stream.get("channels", "unknown")
            self.info(f"Audio Stream {idx + 1}: {codec}, {channels} channels, Language: {language}")

        subtitle_streams = [s for s in probe_data["streams"] if s["codec_type"] == "subtitle"]
        self.info(f"\nFound {len(subtitle_streams)} subtitle stream(s):")
        for idx, stream in enumerate(subtitle_streams):
            language = stream.get("tags", {}).get("language", "unknown")
            codec = stream.get("codec_name", "unknown")
            self.info(f"Subtitle Stream {idx + 1}: {codec}, Language: {language}")

    def log_encoding_start(self, output_file, target_bitrate, cmd):
        self.info("\n=== Starting Encoding Process ===")
        self.info(f"Output File: {output_file}")
        self.info(f"Target Bitrate: {target_bitrate/1_000_000:.2f} Mbps")
        self.info("FFmpeg Command:")
        self.info(" ".join(cmd))

    def log_encoding_complete(self, input_file, output_file, encoding_duration):
        input_size = input_file.stat().st_size / (1024 * 1024 * 1024)  # GB
        output_size = output_file.stat().st_size / (1024 * 1024 * 1024)  # GB
        compression_ratio = input_size / output_size if output_size > 0 else 0

        self.info("\n=== Encoding Complete ===")
        self.info(f"Input Size: {input_size:.2f} GB")
        self.info(f"Output Size: {output_size:.2f} GB")
        self.info(f"Compression Ratio: {compression_ratio:.2f}:1")
        self.info(f"Encoding Duration: {encoding_duration/3600:.2f} hours")
        self.info(f"Average Processing Speed: {(input_size*1024)/(encoding_duration/60):.2f} MB/minute")

    def log_verification(self, output_file):
        verify_cmd = ["ffprobe", "-v", "error", "-i", str(output_file), "-show_streams", "-show_format"]
        try:
            verify_output = subprocess.run(verify_cmd, check=True, capture_output=True, text=True)
            if verify_output.stderr:
                self.warning("Output file verification: WARNING")
                self.warning(verify_output.stderr.strip())
            else:
                self.info("Output file verification: PASSED")
        except subprocess.CalledProcessError as e:
            self.error("Output file verification: FAILED")
            self.error(f"Command: {' '.join(e.cmd)}")
            self.error(f"Return code: {e.returncode}")
            if e.stderr:
                self.error(e.stderr.strip())
            self.error("Ignoring verification error and continuing...")

    def log_final_stats(self, start_time):
        total_duration = time.time() - start_time
        self.info(f"\nTotal Processing Time: {total_duration/3600:.2f} hours")
        self.info("=== Processing Completed Successfully ===")
