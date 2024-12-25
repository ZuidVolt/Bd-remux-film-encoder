dolby_vision_metadata: list[str] = [
    "-map_metadata",
    "0",
    # macOS specific metadata
    "-metadata:s:v",
    "hdr_version=1.0",  # Explicit HDR version
    "-metadata:s:v",
    "mastering_display_metadata_present=1",  # Explicit HDR metadata flag
    "-metadata:s:v",
    "encoder=hevc_videotoolbox",  # Explicit encoder info
    # Color volume metadata (helps with Retina display mapping)
    "-metadata:s:v",
    "BT.2020_compatibility=1",
    "-metadata:s:v",
    "max_content_light_level=1000",
    "-metadata:s:v",
    "max_frame_average_light_level=400",
    "-metadata:s:v",
    "apple_hdr_profile=8.4",  # Helps with Apple devices HDR handling
    "-metadata:s:v",
    "apple_display_primaries=bt2020",  # Explicit Apple color primaries
    # new audio metadata
    "-metadata:s:a",
    "encoder=FFmpeg",
    "-metadata:s:a",
    "dolby_digital_plus=1",
    "-metadata:s:a",
    "dolby_atmos=1",
    "-metadata:s:a",
    "spatial_audio=1",
    "-metadata:s:a",
    "apple_spatial_audio=1",
    # new caption metadata
    "-map_chapters",
    "0",
    # new muxing queue size
    "-max_muxing_queue_size",
    "4096",
]


hevc_metadata: list[str] = [
    "-map_metadata",
    "0",
    # macOS specific metadata
    "-metadata:s:v",
    "encoder=hevc_videotoolbox",  # Explicit encoder info
    # Color volume metadata (helps with Retina display mapping)
    "-metadata:s:v",
    "BT.2020_compatibility=1",
    "-metadata:s:v",
    "max_content_light_level=1000",
    "-metadata:s:v",
    "max_frame_average_light_level=400",
    "-metadata:s:v",
    "apple_hdr_profile=8.4",  # Helps with Apple devices HDR handling
    "-metadata:s:v",
    "apple_display_primaries=bt2020",  # Explicit Apple color primaries
    # new audio metadata
    "-metadata:s:a",
    "encoder=FFmpeg",
    "-metadata:s:a",
    "dolby_digital_plus=1",
    "-metadata:s:a",
    "dolby_atmos=1",
    "-metadata:s:a",
    "spatial_audio=1",
    "-metadata:s:a",
    "apple_spatial_audio=1",
    # new caption metadata
    "-map_chapters",
    "0",
    # new muxing queue size
    "-max_muxing_queue_size",
    "4096",
]
