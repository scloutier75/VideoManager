import json
import subprocess
from pathlib import Path
from typing import Optional


VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".3gp", ".ogv", ".ts", ".m2ts",
    ".mts", ".vob", ".divx", ".rm", ".rmvb",
}


def probe_video(filepath: str) -> Optional[dict]:
    """Run ffprobe and return parsed JSON, or None on failure."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        filepath,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def _parse_frame_rate(fps_str: str) -> float:
    try:
        num, den = fps_str.split("/")
        return float(num) / float(den) if float(den) != 0 else 0.0
    except Exception:
        return 0.0


def calculate_quality_score(video_info: dict) -> tuple[float, dict]:
    """
    Score a video 0-10 based on four weighted components:
      - Resolution  (0-4 pts): based on video height
      - Bitrate     (0-3 pts): bits per pixel per second vs. resolution
      - Codec       (0-2 pts): modern codecs score higher
      - Audio       (0-1 pt):  presence and codec quality
    """
    width = video_info.get("width") or 0
    height = video_info.get("height") or 0
    video_codec = (video_info.get("video_codec") or "").lower()
    video_bitrate = video_info.get("video_bitrate") or 0
    audio_codec = (video_info.get("audio_codec") or "").lower()

    # 1. Resolution score
    if height >= 2160:
        res_score = 4.0
    elif height >= 1440:
        res_score = 3.5
    elif height >= 1080:
        res_score = 3.0
    elif height >= 720:
        res_score = 2.0
    elif height >= 480:
        res_score = 1.0
    elif height >= 360:
        res_score = 0.7
    elif height > 0:
        res_score = 0.5
    else:
        res_score = 0.0

    # 2. Bitrate quality: bits per pixel per second
    if width > 0 and height > 0 and video_bitrate > 0:
        bpps = video_bitrate / (width * height)
        if bpps >= 8.0:
            bitrate_score = 3.0
        elif bpps >= 4.0:
            bitrate_score = 2.5
        elif bpps >= 2.0:
            bitrate_score = 2.0
        elif bpps >= 1.0:
            bitrate_score = 1.5
        elif bpps >= 0.5:
            bitrate_score = 1.0
        else:
            bitrate_score = 0.5
    else:
        bitrate_score = 1.0  # unknown bitrate – neutral

    # 3. Codec score
    if video_codec in ("hevc", "h265", "av1"):
        codec_score = 2.0
    elif video_codec in ("vp9",):
        codec_score = 1.8
    elif video_codec in ("h264", "avc1", "x264"):
        codec_score = 1.5
    elif video_codec in ("vp8", "mpeg4", "divx", "xvid", "theora"):
        codec_score = 1.0
    elif video_codec in ("mpeg2video", "mpeg1video", "wmv1", "wmv2", "wmv3"):
        codec_score = 0.5
    else:
        codec_score = 0.8  # unknown codec – neutral

    # 4. Audio score
    if audio_codec:
        lossless = {"flac", "alac", "pcm_s16le", "pcm_s24le", "pcm_s32le"}
        good = {"aac", "opus", "ac3", "eac3", "dts", "truehd"}
        acceptable = {"mp3", "vorbis", "wmav2", "wma"}
        if audio_codec in lossless or audio_codec in good:
            audio_score = 1.0
        elif audio_codec in acceptable:
            audio_score = 0.8
        else:
            audio_score = 0.6
    else:
        audio_score = 0.0

    total = round(min(10.0, res_score + bitrate_score + codec_score + audio_score), 1)

    breakdown = {
        "resolution_score": res_score,
        "bitrate_score": bitrate_score,
        "codec_score": codec_score,
        "audio_score": audio_score,
    }
    return total, breakdown


def extract_video_info(
    probe_data: dict,
    filepath: str,
    file_size: int,
    file_mtime: float,
) -> dict:
    """Convert raw ffprobe output into a flat dict matching the Video model."""
    streams = probe_data.get("streams", [])
    fmt = probe_data.get("format", {})

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    path = Path(filepath)

    width = height = video_codec = video_bitrate = None
    frame_rate = None
    if video_stream:
        width = video_stream.get("width")
        height = video_stream.get("height")
        video_codec = video_stream.get("codec_name")
        fps_raw = video_stream.get("r_frame_rate", "0/1")
        frame_rate = round(_parse_frame_rate(fps_raw), 3)

        vbr_raw = video_stream.get("bit_rate")
        if vbr_raw and vbr_raw != "N/A":
            video_bitrate = int(vbr_raw)
        else:
            fbr_raw = fmt.get("bit_rate")
            if fbr_raw and fbr_raw != "N/A":
                video_bitrate = int(fbr_raw)

    audio_codec = audio_bitrate = None
    if audio_stream:
        audio_codec = audio_stream.get("codec_name")
        abr_raw = audio_stream.get("bit_rate")
        if abr_raw and abr_raw != "N/A":
            abr = int(abr_raw)
            # Discard sentinel values (e.g. 0xFFFFFFFF) and physically impossible rates
            audio_bitrate = abr if 0 < abr < 100_000_000 else None

    duration = None
    dur_raw = fmt.get("duration") or (video_stream or {}).get("duration")
    if dur_raw and dur_raw != "N/A":
        duration = float(dur_raw)

    container_format = fmt.get("format_name")

    base_info = {
        "filename": path.name,
        "filepath": str(filepath),
        "directory": str(path.parent),
        "file_size": file_size,
        "file_mtime": file_mtime,
        "duration": duration,
        "width": width,
        "height": height,
        "video_codec": video_codec,
        "video_bitrate": video_bitrate,
        "audio_codec": audio_codec,
        "audio_bitrate": audio_bitrate,
        "frame_rate": frame_rate,
        "container_format": container_format,
    }

    score, breakdown = calculate_quality_score(base_info)
    base_info["score"] = score
    base_info["score_breakdown"] = breakdown

    # efficiency_score: quality score relative to expected bitrate for this resolution.
    #   efficiency = score × (reference_mbps / actual_mbps)
    #   > 1× reference → efficient (good quality, low bitrate); < 1× → bloated.
    #   Reference bitrates represent a good-quality encode at each resolution.
    base_info["efficiency_score"] = _compute_efficiency(
        score=score,
        video_bitrate=video_bitrate,
        height=height,
    )

    return base_info


# Reference bitrates (Mbps) for a well-encoded file at each resolution tier.
# These reflect modern codec expectations (H.265/H.264 blended average).
_RESOLUTION_REFERENCE_MBPS = [
    (2160, 15.0),  # 4K
    (1440, 8.0),   # 2K
    (1080, 5.0),   # 1080p
    (720,  2.5),   # 720p
    (480,  1.0),   # 480p
    (360,  0.5),   # 360p
    (0,    0.3),   # lower
]


def _compute_efficiency(score, video_bitrate, height) -> Optional[float]:
    if score is None or not video_bitrate or video_bitrate <= 0 or not height:
        return None
    reference_mbps = next(
        ref for (h, ref) in _RESOLUTION_REFERENCE_MBPS if height >= h
    )
    actual_mbps = video_bitrate / 1_000_000
    return round(score * (reference_mbps / actual_mbps), 2)
