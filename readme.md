
# BD Remux Film Encoder

A high-performance Python-based tool optimized for Apple Silicon Macs, designed to encode and remux Blu-ray discs into more compact and playable formats while maintaining exceptional quality.

Disclaimer: This tool is my personal project is expected to be full of bad practices and bad code (and a lot of bugs). It's not intended for production use without major modiﬁcations.

## 🚀 Features

- **Apple Silicon Optimization**: Leverages Apple Silicon's hardware acceleration for maximum performance
- **Smart Encoding**: Intelligent bitrate calculation based on target file size
- **Multi-Stream Support**: Handles multiple audio tracks and subtitle streams
- **Dolby Vision Support**: Preserves Dolby Vision metadata when available
- **Hardware Acceleration**: Utilizes VideoToolbox for optimal encoding performance
- **Quality Preservation**: Maintains high quality while achieving significant file size reduction
- **Batch Processing**: Support for processing multiple files sequentially
- **Progress Tracking**: Real-time encoding progress and ETA display
- **Flexible Output**: Customizable output formats and encoding settings
- **Error Handling**: Robust error handling and logging system
- **Configurable Settings**: Allows users to customize encoding settings and presets

## 📋 Requirements

### System Requirements

- macOS 11.0 (Big Sur) or later
- Apple Silicon processor (M1, M1 Pro, M1 Max, M1 Ultra, M2, or newer)
- Minimum 8GB RAM (16GB recommended for 4K content)
- Sufficient storage space (at least 3x the size of the source file)

### Software Dependencies

- Python 3.8 or later
- FFmpeg 5.0+ with VideoToolbox support
- FFprobe
- pip (Python package installer)

## 🛠 Installation

1. **Clone the Repository**

   ```bash
   git clone https://github.com/ZuidVolt/BD-remux-film-encoder.git
   cd BD-remux-film-encoder
   ```

2. **Set Up Virtual Environment (Recommended)**

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Install FFmpeg with VideoToolbox Support**

   ```bash
   brew install ffmpeg
   ```

## 💻 Usage

### Environment Variables

Create a `.env` file in the project root with the following options:

```ini
# Required Settings
INPUT_FILE=/path/to/input
OUTPUT_FILE=/path/to/output
```

### Basic Usage

```bash
python main.py
```

or

```bash
make run
```

### Advanced Usage

You can change the config in the main.py file and see all the available settings in the config class in utils.py

## ⚙️ Configuration

### Encoding Presets

| Preset | Quality | Speed | File Size |
|--------|---------|--------|-----------|
| fast | Low | Fastest | Largest |
| medium | Good | Balanced | Balanced |
| slow | Better | Slower | Smaller |

### Configurable Settings

- `target_size_gb`: Target file size in GB
- `preset`: Encoding preset (fast, medium, slow)
- `maintain_dolby_vision`: Preserve Dolby Vision metadata
- `copy_audio`: Copy audio streams
- `copy_subtitles`: Copy subtitle streams
- `english_audio_only`: Only include English audio streams
- `english_subtitles_only`: Only include English subtitle streams
- `use_hardware_acceleration`: Use hardware acceleration
- `hardware_encoder`: Hardware encoder to use
- `fallback_encoder`: Fallback encoder to use
- `quality_preset`: Quality preset for encoding
- `allow_sw_fallback`: Allow software fallback for encoding
- `audio_codec`: Audio codec to use
- `audio_bitrate`: Audio bitrate to use
- `audio_channel`: Audio channel layout to use
- `min_video_bitrate`: Minimum video bitrate to use
- `max_video_bitrate`: Maximum video bitrate to use
- `hdr_params`: HDR parameters to use
- `realtime`: Real-time encoding mode
- `b_frames`: Number of B-frames to use

## 🔍 Advanced Features

### Hardware Acceleration

The encoder automatically detects and utilizes Apple Silicon's hardware acceleration capabilities through VideoToolbox. This provides significant performance improvements:

- Up to 5x faster encoding for 1080p content
- Up to 3x faster encoding for 4K content
- Reduced power consumption
- Lower CPU utilization

### Quality Control

- Smart bitrate calculation based on content complexity
- Dynamic frame analysis for optimal quality
- Automatic HDR metadata preservation
- Dolby Vision profile detection and handling

## 🚨 Troubleshooting

### Common Issues

1. **Encoding Speed is Slow**
   - Ensure VideoToolbox is properly configured
   - Check system resource usage
   - Consider using a faster preset

2. **High Memory Usage**
   - Reduce the number of concurrent tasks
   - Increase swap file size

3. **Output File Larger Than Expected**
   - Verify target size settings
   - Check audio stream selection
   - Consider using a different preset

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📊 Performance Benchmarks

| Content Type | Source Size | Output Size | Encoding Time | Quality Loss |
|--------------|-------------|-------------|---------------|--------------|
| 1080p Movie | 30GB | 5GB | ~58 mins | Negligible |
| 4K HDR Movie | 60GB | 7GB | ~58 mins | Minimal |
| 4K DV Movie | 80GB | 11GB | ~58 mins | noticeable |

- _Times measured on M3 with 16GB RAM_

## 🙏 Acknowledgments

- FFmpeg team for their incredible tools
- Apple for VideoToolbox framework
- Contributors and testers

## 📫 Support

For support, please:

1. Check the [Documentation](docs/README.md)
2. Search [existing issues](https://github.com/ZuidVolt/BD-remux-film-encoder/issues)
3. Create a new issue if needed

---
Made with ❤️ for the video encoding community

## License

This project is licensed under the Apache License, Version 2.0 with important additional terms, including specific commercial use conditions. Users are strongly advised to read the full [LICENSE](LICENSE) file carefully before using, modifying, or distributing this work. The additional terms contain crucial information about liability, data collection, indemnification, and commercial usage requirements that may significantly affect your rights and obligations.

---

🔍 Keywords:
Blu-ray encoding, video compression, FFmpeg, Python automation, macOS optimization, Apple Silicon, M1/M2 optimization, VideoToolbox, hardware acceleration, video transcoding, Dolby Vision, HDR preservation, media processing, remuxing, batch encoding, high-quality compression, video archival, multimedia tools, AV1 encoding, HEVC/H.265, video quality optimization
