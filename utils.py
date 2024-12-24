# utils.py
from typing import Optional, TypedDict, Any
from enum import Enum


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


class EncodingPresetVideotoolbox(Enum):
    LOW = "low"
    MEDIUM = "medium"
    SLOW = "slow"


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
        quality_preset: EncodingPresetVideotoolbox = EncodingPresetVideotoolbox.MEDIUM,
        allow_sw_fallback: bool = True,
        audio_codec: str = "aac",
        audio_bitrate: str = "384k",
        audio_channel: str = "4",
        min_video_bitrate: int = 8_000_000,  # 8 Mbps
        max_video_bitrate: int = 30_000_000,  # 30 Mbps
        hdr_params: Optional[dict[str, str]] = None,
        realtime: str = "false",
        b_frames: str = "6",
        pix_fmt: str = "p010le",
        profile_v: str = "main10",
        max_ref_frames: str = "4",
        group_of_pictures: str = "140",
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
        self.pix_fmt = pix_fmt
        self.profile_v = profile_v
        self.max_ref_frames = max_ref_frames
        self.group_of_pictures = group_of_pictures
