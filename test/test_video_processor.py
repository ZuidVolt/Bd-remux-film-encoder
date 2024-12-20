# test/test_video_processor.py
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import json
import subprocess
from video_processor import VideoProcessor
from utils import EncodingConfig, ProbeError, EncodingError  # noqa
from custom_logger import CustomLogger as Logger
import pytest

logger = Logger(__name__)


# TODO: NOT fully implemented yet


class TestVideoProcessor(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.mock_probe_data = {
            "format": {
                "size": "1073741824",  # 1GB
                "duration": "3600",  # 1 hour
            },
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "hevc",
                    "width": 3840,
                    "height": 2160,
                    "r_frame_rate": "24/1",
                    "color_transfer": "smpte2084",
                    "color_space": "bt2020nc",
                    "color_primaries": "bt2020",
                    "bits_per_raw_sample": 10,
                    "profile": "Main 10",
                    "index": 0,
                },
                {"codec_type": "audio", "codec_name": "aac", "index": 1, "tags": {"language": "eng"}},
            ],
        }

        # Create a mock path that "exists"
        self.mock_input_path = Path("/fake/path/video.mkv")

        # Create patcher for common Path methods
        self.path_exists_patcher = patch("pathlib.Path.exists")
        self.path_is_file_patcher = patch("pathlib.Path.is_file")
        self.shutil_which_patcher = patch("shutil.which")

        # Start the patchers
        self.mock_exists = self.path_exists_patcher.start()
        self.mock_is_file = self.path_is_file_patcher.start()
        self.mock_which = self.shutil_which_patcher.start()

        # Set default return values
        self.mock_exists.return_value = True
        self.mock_is_file.return_value = True
        self.mock_which.return_value = True

    def tearDown(self):
        """Clean up after each test method."""
        self.path_exists_patcher.stop()
        self.path_is_file_patcher.stop()
        self.shutil_which_patcher.stop()

    def test_initialization(self):
        """Test VideoProcessor initialization."""
        # Test successful initialization
        processor = VideoProcessor(self.mock_input_path)
        assert processor.input_file == self.mock_input_path
        assert isinstance(processor.config, EncodingConfig)

        # Test file not found
        self.mock_exists.return_value = False
        with pytest.raises(FileNotFoundError):
            VideoProcessor(self.mock_input_path)

        # Test ffmpeg not found
        self.mock_exists.return_value = True
        self.mock_which.return_value = False
        with pytest.raises(OSError):
            VideoProcessor(self.mock_input_path)

    @patch("subprocess.run")
    def test_probe_file(self, mock_run):
        """Test file probing functionality."""
        mock_run.return_value = MagicMock(stdout=json.dumps(self.mock_probe_data), returncode=0)

        processor = VideoProcessor(self.mock_input_path)
        probe_data = processor.probe_file()

        assert probe_data == self.mock_probe_data
        assert processor.input_size_gb == 1.0
        assert processor.duration == 3600.0

        # Test probe failure
        mock_run.side_effect = subprocess.CalledProcessError(1, [])
        with pytest.raises(ProbeError):
            processor.probe_file()

    def test_calculate_bitrate(self):
        """Test bitrate calculation logic."""
        processor = VideoProcessor(self.mock_input_path)
        processor.probe_data = self.mock_probe_data  # type: ignore
        processor.duration = 3600.0
        processor.video_metadata = {
            "codec_name": "hevc",
            "height": 2160,
            "width": 3840,
            "frame_rate": 24,
            "is_hdr10": True,
            "is_hlg": False,
            "has_dovi": False,
            "bits_per_raw_sample": 10,
        }

        bitrate = processor._calculate_bitrate()

        # Assert bitrate is within expected range
        assert bitrate > processor.config.min_video_bitrate
        assert bitrate <= processor.config.max_video_bitrate

    @patch("subprocess.run")
    def test_build_command(self, mock_run):
        """Test FFmpeg command building."""
        processor = VideoProcessor(self.mock_input_path)
        processor.probe_data = self.mock_probe_data  # type: ignore
        processor.hw_support = True

        # Mock hardware encoder check
        mock_run.return_value = MagicMock(stdout="hevc_videotoolbox")

        output_path = Path("/fake/output/video.mkv")
        target_bitrate = 10000000  # 10 Mbps

        cmd = processor._build_command(output_path, target_bitrate)

        # Verify command structure
        assert cmd[0] == "ffmpeg"
        assert "-i" in cmd
        assert str(self.mock_input_path) in cmd
        assert str(output_path) in cmd
        assert "-b:v" in cmd

    # def test_encode(self):
    #     """Test encoding process."""

    def test_get_stream_indexes(self):
        """Test stream index extraction."""
        processor = VideoProcessor(self.mock_input_path)
        processor.probe_data = self.mock_probe_data  # type: ignore

        indexes = processor._get_stream_indexes()

        assert "video" in indexes
        assert "audio" in indexes
        assert "subtitle" in indexes
        assert indexes["video"] == [0]
        assert indexes["audio"] == [1]
        assert indexes["subtitle"] == []


if __name__ == "__main__":
    unittest.main()
