"""Persistent, explicitly allowlisted evidence for graphical test runs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_ROOT = Path(os.environ.get("STARCOASTER_ARTIFACT_ROOT", ROOT / "run-data/artifacts"))
LOG_NAMES = {"client-a.log", "client-b.log", "server.log", "zerg.log", "terran.log", "bwapi.log",
             "bwapi-restart.log", "video-capture.log"}
VIDEO_NAMES = {"combined.mp4", "client-a.mp4", "client-b.mp4"}
IMAGE_NAME = re.compile(r"(?:client-[ab]-(?:initial|firing|death|damage|early|later|final|overview|approach|combat|carousel-(?:attack|destroyed)|shop-(?:attack|destroyed)|ferris-(?:attack|destroyed)|t[\d.]+)(?:-rot[0-3])?|frame-\d+|park-background)\.png\Z")
DIAGNOSTIC_NAMES = {"navigation-grid.png", "planned-paths.png", "observed-paths.png",
                    "navigation-grid.json", "planned-paths.json", "observed-paths.json",
                    "target-events.json", "navigation-events.json", "violations.json"}
ID_PATTERN = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{12}\Z")


def run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(6)


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".run-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _snapshot(directory: Path) -> dict[str, tuple[int, int]]:
    if not directory.exists():
        return {}
    return {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in directory.iterdir()
            if p.is_file() and not p.is_symlink()}


class ArtifactRun:
    def __init__(self, kind: str, title: str, output: Path | None = None,
                 root: Path | None = None, config: dict | None = None):
        if kind not in ("live-capture", "battle-replay"):
            raise ValueError("invalid run type")
        self.root = Path(root or ARTIFACT_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)
        for _ in range(10):
            ident = run_id()
            try:
                (self.root / ident).mkdir()
                break
            except FileExistsError:
                continue
        else:
            raise FileExistsError("could not allocate a unique artifact run")
        self.directory = self.root / ident
        self.output = Path(output) if output is not None else self.directory
        self.legacy = self.output.resolve() != self.directory.resolve()
        self.before = _snapshot(self.output) if self.legacy else {}
        self.output.mkdir(parents=True, exist_ok=True)
        try:
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                          text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            sha = ""
        self.manifest = {
            "schema_version": 1, "id": ident, "type": kind, "title": title,
            "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None, "commit_sha": sha, "videos": [], "screenshots": [],
            "verification_file": None, "video_metadata_file": None, "logs": [], "diagnostics": [],
            "scenario_config_file": None,
            "error": None, "capture_config": config or {}, "size_bytes": 0,
        }
        atomic_json(self.directory / "run.json", self.manifest)

    def _changed(self, path: Path) -> bool:
        return not self.legacy or self.before.get(path.name) != (path.stat().st_mtime_ns, path.stat().st_size)

    def _copy(self, path: Path) -> None:
        if not self.legacy:
            return
        target = self.directory / path.name
        with path.open("rb") as source, tempfile.NamedTemporaryFile(dir=self.directory, delete=False) as temporary:
            shutil.copyfileobj(source, temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
            temp_name = temporary.name
        os.replace(temp_name, target)

    def finalize(self, status: str, error: str | None = None) -> dict:
        if status not in ("passed", "failed", "interrupted"):
            raise ValueError("invalid final status")
        metadata = {}
        metadata_path = self.output / "video-metadata.json"
        if metadata_path.is_file() and not metadata_path.is_symlink() and self._changed(metadata_path):
            try:
                metadata = json.loads(metadata_path.read_text())
            except (OSError, ValueError):
                metadata = {}
        valid_videos = {item.get("filename") for item in metadata.get("outputs", [])
                        if isinstance(item, dict) and "duration_seconds" in item and not item.get("validation_error")}
        if metadata.get("filename") in VIDEO_NAMES and metadata.get("duration_seconds"):
            valid_videos.add(metadata["filename"])
        videos, screenshots, logs, diagnostics = [], [], [], []
        sizes = 0
        candidates = list(self.output.iterdir())
        for path in candidates:
            if not path.is_file() or path.is_symlink() or not self._changed(path):
                continue
            name = path.name
            if name in VIDEO_NAMES and name in valid_videos:
                group = videos
                label = name.removesuffix(".mp4").replace("-", " ").title()
            elif IMAGE_NAME.fullmatch(name):
                group = screenshots
                label = name.removesuffix(".png").replace("-", " ").title()
            elif name in DIAGNOSTIC_NAMES:
                group = diagnostics
                label = name.rsplit(".", 1)[0].replace("-", " ").title()
            elif name in LOG_NAMES:
                # Logs are often noisy and can include environment data. Publish a
                # small diagnostic excerpt with obvious secret-bearing lines removed.
                filtered = []
                for line in path.read_text(errors="replace").splitlines():
                    if not re.search(r"token|secret|password|authorization|cookie|api[_-]?key", line, re.I):
                        filtered.append(line[:1000])
                data = ("\n".join(filtered)[-65536:] + "\n").encode()
                diagnostic_name = "diagnostic-" + name
                (self.directory / diagnostic_name).write_bytes(data)
                logs.append({"path": diagnostic_name, "label": name})
                sizes += len(data)
                continue
            elif name in ("verification.json", "video-metadata.json", "scenario-config.json"):
                group = None
                label = ""
            else:
                continue
            self._copy(path)
            sizes += (self.directory / name).stat().st_size
            if group is not None:
                group.append({"path": name, "label": label})
        screenshots.sort(key=lambda item: (self.directory / item["path"]).stat().st_mtime_ns)
        self.manifest.update({"status": status, "finished_at": datetime.now(timezone.utc).isoformat(),
                              "error": error, "videos": videos, "screenshots": screenshots,
                              "diagnostics": diagnostics,
                              "logs": logs, "size_bytes": sizes,
                              "verification_file": "verification.json" if (self.directory / "verification.json").is_file() else None,
                              "video_metadata_file": "video-metadata.json" if (self.directory / "video-metadata.json").is_file() else None,
                              "scenario_config_file": "scenario-config.json" if (self.directory / "scenario-config.json").is_file() else None})
        atomic_json(self.directory / "run.json", self.manifest)
        return self.manifest
