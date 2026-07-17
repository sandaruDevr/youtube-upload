import logging
import subprocess
import shutil
from pathlib import Path

from .config import settings

logger = logging.getLogger(__name__)

TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)


def _check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _run_ffmpeg(args: list[str]) -> None:
    cmd = ["ffmpeg", "-y", *args]
    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("ffmpeg stderr: %s", result.stderr)
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")


def process_video(input_path: Path, output_path: Path) -> Path:
    """Process a video into YouTube Shorts format (1080x1920, <=60s, with music)."""
    if not _check_ffmpeg():
        raise RuntimeError("ffmpeg is not installed or not in PATH")

    music_path = settings.music_path

    # Build filter: scale to 1080x1920 with padding, trim to 60s, replace audio with music
    # Shorts are vertical 9:16 at 1080x1920
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
        "setsar=1"
    )

    args = [
        "-i", str(input_path),
    ]

    if music_path.exists():
        args.extend(["-i", str(music_path)])
        args.extend([
            "-filter_complex", f"[0:v]{vf}[v];[1:a]atrim=0:60,asetpts=PTS-STARTPTS[a]",
            "-map", "[v]",
            "-map", "[a]",
            "-c:a", "aac",
            "-b:a", "128k",
        ])
    else:
        logger.warning("No music track found at %s — keeping original audio", music_path)
        args.extend([
            "-vf", vf,
            "-c:a", "aac",
            "-b:a", "128k",
        ])

    args.extend([
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "28",
        "-threads", "1",
        "-r", "30",
        "-t", "60",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ])

    _run_ffmpeg(args)
    return output_path


def process_image(input_path: Path, output_path: Path, duration: int = 30) -> Path:
    """Convert an image into a YouTube Shorts video (1080x1920, with music)."""
    if not _check_ffmpeg():
        raise RuntimeError("ffmpeg is not installed or not in PATH")

    music_path = settings.music_path

    vf = (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
        "setsar=1"
    )

    if music_path.exists():
        args = [
            "-loop", "1",
            "-i", str(input_path),
            "-i", str(music_path),
            "-filter_complex", f"[0:v]{vf},format=yuv420p[v];[1:a]atrim=0:{duration},asetpts=PTS-STARTPTS[a]",
            "-map", "[v]",
            "-map", "[a]",
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-threads", "1",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
    else:
        logger.warning("No music track found at %s — generating silent audio", music_path)
        args = [
            "-loop", "1",
            "-i", str(input_path),
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-vf", f"{vf},format=yuv420p",
            "-map", "0:v",
            "-map", "1:a",
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-threads", "1",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]

    _run_ffmpeg(args)
    return output_path
