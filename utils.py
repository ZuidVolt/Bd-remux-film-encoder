# utils.py
from enum import Enum
from typing import Any, TypedDict
from pydantic import BaseModel, Field


class EncoderError(Exception):
    pass


class ProbeError(EncoderError):
    pass


class EncodingError(EncoderError):
    pass


class EncodingPreset(str, Enum):
    ULTRAFAST = "ultrafast"
    SUPERFAST = "superfast"
    VERYFAST = "veryfast"
    FASTER = "faster"
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"
    SLOWER = "slower"
    VERYSLOW = "veryslow"


class EncodingPresetVideotoolbox(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    SLOW = "slow"


# Keep TypedDict for ProbeData to maintain indexing compatibility
class RequiredStreamFields(TypedDict):
    index: int
    codec_type: str


class OptionalStreamFields(TypedDict, total=False):
    codec_name: str
    height: int
    width: int
    color_space: str
    color_transfer: str
    color_primaries: str
    r_frame_rate: str
    tags: dict[str, str]


class StreamDict(RequiredStreamFields, OptionalStreamFields):
    pass


class ProbeData(TypedDict):
    streams: list[StreamDict]
    format: dict[str, Any]


class EncodingStatus(Enum):  # to be added to the VideoProcessor class
    INITIALIZING = "initializing"
    ANALYZING = "analyzing"
    ENCODING = "encoding"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


# Use TypedDict for HDRParams to maintain dictionary-like access
class HDRParams(TypedDict):
    max_cll: str
    master_display: str


class EncodingConfig(BaseModel):
    target_size_gb: float = Field(default=25.0)
    preset: EncodingPreset = Field(default=EncodingPreset.MEDIUM)
    maintain_dolby_vision: bool = Field(default=True)
    copy_audio: bool = Field(default=True)
    copy_subtitles: bool = Field(default=True)
    english_audio_only: bool = Field(default=False)
    english_subtitles_only: bool = Field(default=False)
    use_hardware_acceleration: bool = Field(default=True)
    hardware_encoder: str = Field(default="hevc_videotoolbox")
    fallback_encoder: str = Field(default="libx265")
    quality_preset: EncodingPresetVideotoolbox = Field(default=EncodingPresetVideotoolbox.MEDIUM)
    allow_sw_fallback: bool = Field(default=True)
    audio_codec: str = Field(default="aac")
    audio_bitrate: str = Field(default="384k")
    audio_channel: str = Field(default="4")
    min_video_bitrate: int = Field(default=8_000_000)  # 8 Mbps
    max_video_bitrate: int = Field(default=30_000_000)  # 30 Mbps
    hdr_params: dict[str, str] = Field(
        default_factory=lambda: {
            "max_cll": "1000,400",
            "master_display": "G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,50)",
        },
    )
    realtime: str = Field(default="false")
    b_frames: str = Field(default="6")
    pix_fmt: str = Field(default="p010le")
    profile_v: str = Field(default="main10")
    max_ref_frames: str = Field(default="4")
    group_of_pictures: str = Field(default="140")

    class Config:
        arbitrary_types_allowed: bool = True
