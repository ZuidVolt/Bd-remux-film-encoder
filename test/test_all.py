import pytest
from unittest.mock import patch
from pathlib import Path
from video_processor import VideoProcessor, EncodingConfig, EncodingError


# 1. Unit Tests
class TestVideoProcessor:
    @pytest.fixture
    def mock_config(self):
        return EncodingConfig(
            target_size_gb=4.0,
            maintain_dolby_vision=True,
            copy_audio=True,
            copy_subtitles=True,
        )

    @pytest.fixture
    def processor(self, mock_config, tmp_path):
        input_file = tmp_path / "test.mp4"
        input_file.write_bytes(b"dummy content")
        return VideoProcessor(input_file, mock_config)

    def test_probe_file(self, processor):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = '{"format": {"size": "1000000", "duration": "60"}}'
            probe_data = processor.probe_file()
            assert probe_data["format"]["duration"] == "60"

    def test_calculate_bitrate(self, processor):
        processor.duration = 60
        processor.input_size_gb = 1.0
        processor.video_metadata = {
            "height": 1080,
            "has_dovi": False,
            "is_hdr10": False,
            "frame_rate": 30,
            "bits_per_raw_sample": 8,
            "codec_name": "h264",
        }
        bitrate = processor._calculate_bitrate()
        assert isinstance(bitrate, int)
        assert bitrate > 0


# 2. Integration Tests
class TestVideoProcessorIntegration:
    @pytest.mark.integration
    def test_end_to_end_encoding(self, tmp_path):
        # Create a small test video file
        input_file = tmp_path / "input.mp4"
        output_file = tmp_path / "output.mp4"

        config = EncodingConfig(
            target_size_gb=1.0,
            maintain_dolby_vision=False,
            copy_audio=True,
            copy_subtitles=True,
        )

        processor = VideoProcessor(input_file, config)
        processor.encode(output_file)

        assert output_file.exists()
        assert output_file.stat().st_size > 0


# 3. Performance Tests
class TestVideoProcessorPerformance:
    @pytest.mark.benchmark
    def test_encoding_performance(self, benchmark, processor):
        def encode_sample():
            processor.encode(Path("test_output.mp4"))

        result = benchmark(encode_sample)
        assert result.mean < 5.0  # Should complete within 5 seconds


# 4. Error Case Tests
def test_invalid_input_file():
    with pytest.raises(FileNotFoundError):
        VideoProcessor(Path("nonexistent.mp4"), EncodingConfig())


def test_encoding_failure():
    with pytest.raises(EncodingError):
        processor = VideoProcessor(Path("test.mp4"), EncodingConfig())
        processor.encode(Path("invalid/path/output.mp4"))


# 5. Mocking External Dependencies
@patch("subprocess.run")
@patch("subprocess.Popen")
def test_ffmpeg_calls(mock_popen, mock_run, processor):
    mock_run.return_value.stdout = "{}"
    mock_popen.return_value.returncode = 0

    processor.encode(Path("output.mp4"))

    assert mock_run.called
    assert mock_popen.called


# 6. Configuration Testing
def test_config_validation():
    with pytest.raises(ValueError):
        EncodingConfig(target_size_gb=-1)  # Invalid size

    config = EncodingConfig(target_size_gb=4.0)
    assert config.target_size_gb == 4.0


# 7. Test Fixtures and Factories
@pytest.fixture
def sample_video_file(tmp_path):
    """Create a sample video file for testing."""
    video_file = tmp_path / "sample.mp4"
    # Create minimal valid MP4 file
    with Path.open(video_file, "wb") as f:
        f.write(b"\x00" * 1024)
    return video_file


@pytest.fixture
def mock_ffprobe_output():
    """Provide mock ffprobe output for testing."""
    return {
        "streams": [
            {
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30/1",
            }
        ],
        "format": {"duration": "60.0", "size": "1073741824"},
    }
