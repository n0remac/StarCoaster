"""Optional FFmpeg recording of the two existing graphical test displays."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
import json
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time


DISPLAYS = {"client-a": ":91.0", "client-b": ":92.0"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class VideoConfig:
    layout: str = "combined"
    fps: int = 10
    width: int = 960
    crf: int = 32
    preset: str = "veryfast"
    input_width: int = 1280
    input_height: int = 800

    def __post_init__(self) -> None:
        if self.layout not in ("single", "combined", "separate"):
            raise ValueError("video layout must be single, combined, or separate")
        if not 1 <= self.fps <= 60:
            raise ValueError("video FPS must be between 1 and 60")
        if self.input_width < 320 or self.input_height < 240:
            raise ValueError("capture display must be at least 320x240")
        if not 2 <= self.width <= self.input_width or self.width % 2:
            raise ValueError("per-client video width must be even and fit the capture display")
        if not 0 <= self.crf <= 51:
            raise ValueError("video CRF must be between 0 and 51")
        if self.preset not in ("ultrafast", "superfast", "veryfast", "faster", "fast",
                               "medium", "slow", "slower", "veryslow", "placebo"):
            raise ValueError("invalid x264 preset")

    @property
    def height(self) -> int:
        # Nearest even height keeps the original aspect ratio as closely as possible.
        return max(2, 2 * round(self.width * self.input_height / self.input_width / 2))

    @property
    def resolution(self) -> tuple[int, int]:
        return (self.width * (2 if self.layout == "combined" else 1), self.height)


def check_dependencies() -> None:
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            raise RuntimeError(f"{binary} is required for --record-video (install ffmpeg)")
    encoders = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                              capture_output=True, text=True)
    if encoders.returncode != 0 or re.search(r"\blibx264\b", encoders.stdout) is None:
        raise RuntimeError("FFmpeg must include the libx264 encoder for --record-video")


def command_for(config: VideoConfig, output: Path, client: str | None = None) -> list[str]:
    if config.layout in ("separate", "single") and client not in DISPLAYS:
        raise ValueError("single or separate recording requires a client")
    if config.layout == "single" and client != "client-a":
        raise ValueError("single recording uses client-a")
    if config.layout == "combined" and client is not None:
        raise ValueError("combined recording has no individual client")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y"]
    displays = DISPLAYS.values() if client is None else (DISPLAYS[client],)
    for display in displays:
        command += ["-f", "x11grab", "-framerate", str(config.fps),
                    "-video_size", f"{config.input_width}x{config.input_height}", "-i", display]
    if client is None:
        filters = (f"[0:v]scale={config.width}:{config.height}:flags=fast_bilinear[a];"
                   f"[1:v]scale={config.width}:{config.height}:flags=fast_bilinear[b];"
                   "[a][b]hstack=inputs=2[v]")
        command += ["-filter_complex", filters, "-map", "[v]"]
    else:
        command += ["-vf", f"scale={config.width}:{config.height}:flags=fast_bilinear"]
    command += ["-an", "-c:v", "libx264", "-preset", config.preset,
                "-crf", str(config.crf), "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(output)]
    return command


def probe_video(path: Path, expected: tuple[int, int]) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-show_entries",
         "stream=codec_name,width,height,avg_frame_rate,nb_read_frames:format=duration",
         "-of", "json", str(path)], capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    stream = next((item for item in streams if item.get("codec_name") == "h264"), None)
    if stream is None or (stream.get("width"), stream.get("height")) != expected:
        raise RuntimeError(f"invalid H.264 video resolution in {path}")
    duration = float(data.get("format", {}).get("duration", 0))
    frames = int(stream.get("nb_read_frames") or 0)
    if duration <= 0 or frames <= 0:
        raise RuntimeError(f"empty or invalid recording: {path}")
    return {"filename": path.name, "file_size_bytes": path.stat().st_size,
            "resolution": list(expected), "duration_seconds": duration,
            "frame_count": frames, "measured_fps": round(frames / duration, 3),
            "stream_fps": str(Fraction(stream["avg_frame_rate"]))}


class VideoRecorder:
    def __init__(self, config: VideoConfig, output_dir: Path):
        self.config = config
        self.output_dir = output_dir
        self.processes: list[tuple[str, Path, subprocess.Popen]] = []
        self.log = None
        self.start_monotonic: float | None = None
        self.start_utc: str | None = None
        self.events: list[dict] = []

    def event(self, kind: str, **details: object) -> None:
        if self.start_monotonic is not None:
            self.events.append({"event": kind,
                                "seconds_from_recording_start": round(time.monotonic() - self.start_monotonic, 3),
                                **details})

    def start(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log = (self.output_dir / "video-capture.log").open("w")
        targets = ([(None, "combined.mp4")] if self.config.layout == "combined" else
                   [("client-a", "client-a.mp4")] if self.config.layout == "single" else
                   [("client-a", "client-a.mp4"), ("client-b", "client-b.mp4")])
        self.start_utc = utc_now()
        self.start_monotonic = time.monotonic()
        try:
            for client, filename in targets:
                path = self.output_dir / filename
                command = command_for(self.config, path, client)
                self.log.write(f"{utc_now()} starting {filename}: {command!r}\n")
                self.log.flush()
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                           stdout=self.log, stderr=subprocess.STDOUT)
                self.processes.append((filename, path, process))
            self.check_alive()
        except BaseException:
            self._stop_processes()
            self.log.close()
            self.log = None
            raise

    def check_alive(self) -> None:
        for filename, _, process in self.processes:
            code = process.poll()
            if code is not None:
                raise RuntimeError(f"FFmpeg for {filename} exited early ({code}); see {self.output_dir / 'video-capture.log'}")

    def _stop_processes(self) -> list[str]:
        errors = []
        interrupted = set()
        for filename, _, process in self.processes:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                interrupted.add(filename)
        for filename, _, process in self.processes:
            try:
                code = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                code = process.wait(timeout=5)
                errors.append(f"{filename}: FFmpeg required forced termination")
            # FFmpeg exits 255 after an orderly SIGINT on this Pi. The file is
            # still validated with ffprobe below before it can count as success.
            if code != 0 and not (code == 255 and filename in interrupted):
                errors.append(f"{filename}: FFmpeg exited with status {code}")
        return errors

    def stop(self, test_success: bool, test_error: str | None = None) -> dict:
        if self.start_monotonic is None:
            raise RuntimeError("video recorder was never started")
        end_monotonic = time.monotonic()
        end_utc = utc_now()
        errors = self._stop_processes()
        finalized_utc = utc_now()
        if self.log is not None:
            self.log.write(f"{finalized_utc} stopped; errors={errors!r}\n")
            self.log.close()
            self.log = None
        outputs = []
        for _, path, _ in self.processes:
            try:
                output = probe_video(path, self.config.resolution)
                output["video_start_offset_seconds_estimate"] = round(max(
                    0, end_monotonic - self.start_monotonic - output["duration_seconds"]), 3)
                outputs.append(output)
            except (OSError, ValueError, ZeroDivisionError, KeyError,
                    subprocess.CalledProcessError, RuntimeError) as error:
                errors.append(f"{path.name}: ffprobe validation failed: {error}")
                if path.exists():
                    outputs.append({"filename": path.name, "file_size_bytes": path.stat().st_size,
                                    "validation_error": str(error)})
        metadata = {
            "capture_start_utc": self.start_utc, "capture_end_utc": end_utc,
            "finalized_utc": finalized_utc,
            "capture_start_monotonic_seconds": self.start_monotonic,
            "recording_duration_seconds": round(end_monotonic - self.start_monotonic, 3),
            "layout": self.config.layout, "resolution": list(self.config.resolution),
            "input_resolution": [self.config.input_width, self.config.input_height],
            "requested_fps": self.config.fps,
            "encoder": {"codec": "libx264", "crf": self.config.crf,
                        "preset": self.config.preset, "pixel_format": "yuv420p"},
            "client_displays": DISPLAYS, "outputs": outputs, "events": self.events,
            "test_status": "passed" if test_success and not errors else "failed",
            "test_error": test_error,
            "recording_errors": errors,
        }
        (self.output_dir / "video-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
        if errors:
            raise RuntimeError("video recording failed: " + "; ".join(errors))
        return metadata
