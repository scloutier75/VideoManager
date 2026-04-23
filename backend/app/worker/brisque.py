"""
Perceptual quality scorer for video frames using BRISQUE.

Workflow:
  1. Use ffmpeg to extract N evenly-spaced frames from the video as PNG files.
  2. Score each frame with the `brisque` package (requires opencv-python-headless).
  3. Take the median raw BRISQUE score and convert to a 0-10 scale (higher = better).

BRISQUE raw scores:
  ~10  → nearly pristine
  ~40  → noticeable quality issues
  ~80+ → severely distorted

Conversion: quality = clamp(10 - raw / 10, 0, 10)
  raw=0  → 10.0,  raw=40 → 6.0,  raw=80 → 2.0
"""

import os
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def _extract_frames(filepath: str, n_frames: int, tmpdir: str) -> list[str]:
    """
    Use ffmpeg to extract n_frames evenly distributed across the video.
    Returns a list of paths to the extracted PNG files (may be fewer than n_frames
    if the video is very short or ffmpeg fails on some).
    """
    # Use select filter to grab frames at equal intervals by presentation timestamp
    # fps=1/(duration/n) is equivalent but select is more reliable across formats
    select_expr = f"not(mod(n\\,{max(1, 1)}))"  # will be overridden below

    # Simpler: use fps filter set to produce ~n_frames over the whole duration
    # We probe duration via ffprobe first
    try:
        probe_cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_entries", "format=duration", filepath
        ]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
        import json
        fmt = json.loads(probe_result.stdout).get("format", {})
        duration = float(fmt.get("duration", 0) or 0)
    except Exception:
        duration = 0

    if duration <= 0:
        # fallback: take a frame every 60s
        fps_filter = "fps=fps=1/60"
    else:
        frame_interval = max(1.0, duration / (n_frames + 1))
        fps_filter = f"fps=fps=1/{frame_interval:.3f}"

    out_pattern = os.path.join(tmpdir, "frame_%04d.png")
    cmd = [
        "ffmpeg", "-y", "-v", "quiet",
        "-i", filepath,
        "-vf", fps_filter,
        "-frames:v", str(n_frames),
        "-vsync", "vfr",
        out_pattern,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600, check=False)
        if result.returncode != 0 and result.stderr:
            logger.warning(
                f"[BRISQUE] ffmpeg non-zero exit ({result.returncode}) for "
                f"{Path(filepath).name}: {result.stderr.decode(errors='replace').strip()}"
            )
    except subprocess.TimeoutExpired:
        logger.warning(
            f"[BRISQUE] ffmpeg timed out (600s) extracting frames from: {Path(filepath).name} "
            f"— try lowering --concurrency if this is a network mount"
        )
        return []
    except FileNotFoundError:
        logger.error("[BRISQUE] ffmpeg not found in PATH")
        return []

    return sorted(str(p) for p in Path(tmpdir).glob("frame_*.png"))


_brisque_instance = None


def _get_brisque():
    """
    Return a BRISQUE instance, lazily initialised and patched for NumPy 2.x.

    NumPy 2.x removed implicit float() conversion of 0-d arrays.  The brisque
    package's scale_features() iterates an object-dtype array of 0-d float64
    arrays and calls float(elem), which now raises TypeError.  We replace
    scale_features with a version that uses .item() instead.
    """
    global _brisque_instance
    if _brisque_instance is not None:
        return _brisque_instance

    from brisque import BRISQUE

    instance = BRISQUE()

    # --- NumPy 2.x compatibility patch ---
    original_scale = instance.scale_features

    def _scale_features_patched(features):
        params = instance.scale_params
        min_ = np.asarray([v.item() if hasattr(v, 'item') else float(v)
                           for v in params['min_']], dtype=np.float64)
        max_ = np.asarray([v.item() if hasattr(v, 'item') else float(v)
                           for v in params['max_']], dtype=np.float64)
        feats = np.asarray([v.item() if hasattr(v, 'item') else float(v)
                            for v in features], dtype=np.float64)
        return -1.0 + (2.0 / (max_ - min_)) * (feats - min_)

    instance.scale_features = _scale_features_patched
    # --- end patch ---

    _brisque_instance = instance
    return instance


def _brisque_frame(frame_path: str) -> Optional[float]:
    """
    Return the raw BRISQUE score for a single frame (lower = better, ~0-100).
    Returns None on any failure.
    """
    try:
        import cv2
        from skimage import io

        scorer = _get_brisque()

        img = io.imread(frame_path)
        if img is None or img.size == 0:
            return None

        # Drop alpha channel if present
        if img.ndim == 3 and img.shape[2] == 4:
            img = img[:, :, :3]

        # Down-scale wide frames for speed (BRISQUE is O(n_pixels))
        h, w = img.shape[:2]
        if w > 1280:
            new_w = 1280
            new_h = int(h * 1280 / w)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

        return float(scorer.score(img))

    except Exception as e:
        logger.warning(
            f"[BRISQUE] Frame scoring failed ({Path(frame_path).name}): "
            f"{type(e).__name__}: {e}"
        )
        return None


def score_video_brisque(filepath: str, n_frames: int = 8) -> tuple[Optional[float], Optional[str]]:
    """
    Compute a BRISQUE-based perceptual quality score for a video, returned on 0-10
    (higher = better).

    Returns a tuple ``(score, failure_reason)``:
      - On success: ``(float, None)``
      - On failure: ``(None, str)`` where *failure_reason* describes what went wrong.
    """
    with tempfile.TemporaryDirectory(prefix="vmgr_brisque_") as tmpdir:
        frame_paths = _extract_frames(filepath, n_frames, tmpdir)
        if not frame_paths:
            reason = "ffmpeg extracted 0 frames (unsupported format, corrupt file, or timeout)"
            logger.warning(f"[BRISQUE] No frames extracted from: {filepath}")
            return None, reason

        raw_scores = []
        for fp in frame_paths:
            s = _brisque_frame(fp)
            if s is not None:
                raw_scores.append(s)

        if not raw_scores:
            reason = (
                f"all {len(frame_paths)} frame(s) failed BRISQUE scoring "
                "(library error, corrupt frames, or missing opencv/skimage)"
            )
            logger.warning(
                f"[BRISQUE] All {len(frame_paths)} frame(s) failed to score for: {Path(filepath).name}"
            )
            return None, reason

        # Use median to reduce influence of scene-cut outliers
        median_raw = float(np.median(raw_scores))
        # Convert raw BRISQUE (lower=better) to 0-10 quality (higher=better)
        quality = round(max(0.0, min(10.0, 10.0 - median_raw / 10.0)), 1)
        logger.debug(
            f"[BRISQUE] {Path(filepath).name}: "
            f"raw_median={median_raw:.1f}  quality={quality} over {len(raw_scores)} frames"
        )
        return quality, None
