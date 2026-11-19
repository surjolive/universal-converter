import shutil
import subprocess
from pathlib import Path


def ffmpeg_path():
    return shutil.which("ffmpeg")


def convert(input_path: Path, output_path: Path, settings: dict):
    binary = ffmpeg_path()
    if not binary:
        raise RuntimeError("FFmpeg is not installed or is not on PATH")
    command = [binary, "-hide_banner", "-y", "-i", str(input_path)]
    width = settings.get("width")
    height = settings.get("height")
    if width or height:
        command += ["-vf", f"scale={width or -2}:{height or -2}"]
    if settings.get("video_bitrate"):
        command += ["-b:v", str(settings["video_bitrate"])]
    if settings.get("audio_bitrate"):
        command += ["-b:a", str(settings["audio_bitrate"])]
    if settings.get("frame_rate"):
        command += ["-r", str(settings["frame_rate"])]
    codec = settings.get("video_codec")
    if codec:
        command += ["-c:v", codec]
    audio_codec = settings.get("audio_codec")
    if audio_codec:
        command += ["-c:a", audio_codec]
    command += [str(output_path)]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=int(settings.get("timeout", 3600)), check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr[-3000:] or "FFmpeg conversion failed")
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("FFmpeg did not create a valid output")
    return {"ffmpeg": binary}
