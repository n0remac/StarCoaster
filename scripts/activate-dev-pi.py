#!/usr/bin/env python3
"""Atomically activate a private DEV Pi release, restoring the old service on failure."""

import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


RELEASE_ROOT = Path("/media/pi/media1/starcoaster-dev-releases")
OVERRIDE = Path.home() / ".config/systemd/user/starcoaster-game.service.d/old-pi.conf"
LEGACY_BUILD = Path("/media/pi/media1/starcoaster-production-build")
LIBRARY = LEGACY_BUILD / "run-data/pi-park-library"
SERVICE = "starcoaster-game.service"
STATUS_URL = "http://127.0.0.1:8091/private/park-session"


def run(*args):
    subprocess.run(args, check=True)


def verify_release(path, revision):
    if not revision or len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("invalid release revision")
    if path.is_symlink() or not path.is_dir() or path.name != revision:
        raise ValueError("release directory missing or unsafe")
    checksums = path / "SHA256SUMS"
    if not checksums.is_file() or checksums.is_symlink():
        raise ValueError("release checksums missing")
    expected = {}
    for line in checksums.read_text().splitlines():
        digest, separator, name = line.partition("  ")
        relative = Path(name)
        if (not separator or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
                or relative.is_absolute() or ".." in relative.parts or name in expected):
            raise ValueError("invalid release checksum entry")
        expected[name] = digest
    actual = {}
    for candidate in path.rglob("*"):
        relative = str(candidate.relative_to(path))
        mutable = relative.startswith("run-data/") and not relative.startswith("run-data/wasm-deploy/current/")
        if mutable:
            continue
        if candidate.is_symlink():
            raise ValueError("symlink in release")
        if candidate.is_file() and candidate != checksums:
            digest = hashlib.sha256()
            with candidate.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b""):
                    digest.update(chunk)
            actual[relative] = digest.hexdigest()
    if actual != expected or (path / "REVISION").read_text().strip() != revision:
        raise ValueError("release checksum or revision mismatch")
    for relative in ("scripts/run-pi-game.sh", "build/world-bridge", "build/wasm-server",
                     "build/openrct2/openrct2-cli", "build/bridge-module/BridgeAIModule.so",
                     "run-data/wasm-deploy/current/manifest.json"):
        if relative not in actual:
            raise ValueError("missing runtime input: " + relative)


def override_text(root, library=LIBRARY):
    return ("[Service]\n"
            f"WorkingDirectory={root}/current\n"
            "ExecStart=\n"
            f"ExecStart=/bin/bash {root}/current/scripts/run-pi-game.sh\n"
            f"Environment=BRIDGE_PARK_LIBRARY={library}\n"
            f"Environment=BRIDGE_WASM_LOG_FILE={root}/logs/wasm-playable-server.log\n")


def replace_file(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".next")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def replace_link(path, target):
    temporary = path.with_name(path.name + ".next")
    temporary.unlink(missing_ok=True)
    if target is None:
        path.unlink(missing_ok=True)
    else:
        temporary.symlink_to(target)
        os.replace(temporary, path)


def check_serving(path):
    pid = subprocess.check_output(
        ["systemctl", "--user", "show", "-p", "MainPID", "--value", SERVICE], text=True).strip()
    if int(pid) <= 0 or Path(f"/proc/{pid}/cwd").resolve() != path.resolve():
        return False
    with urllib.request.urlopen(STATUS_URL, timeout=3) as response:
        json.load(response)
    return True


def serving_revision(path, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if check_serving(path):
                return True
        except (OSError, ValueError, subprocess.CalledProcessError, TimeoutError):
            pass
        time.sleep(1)
    return False


def activate(revision, root=RELEASE_ROOT, override=OVERRIDE):
    root = Path(root)
    candidate = root / "releases" / revision
    verify_release(candidate, revision)
    root.mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    with (root / "activate.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = root / "current"
        if current.exists() and not current.is_symlink():
            raise ValueError("current release is not a symlink")
        previous = current.readlink() if current.is_symlink() else None
        old_override = override.read_bytes() if override.exists() else None
        try:
            replace_link(current, Path("releases") / revision)
            replace_file(override, override_text(root).encode())
            run("systemctl", "--user", "daemon-reload")
            run("systemctl", "--user", "restart", SERVICE)
            if not serving_revision(candidate):
                raise RuntimeError("DEV game service did not serve the new revision")
            if previous and previous != Path("releases") / revision:
                replace_link(root / "previous", previous)
            elif previous is None and old_override is not None:
                replace_file(root / "legacy-service-override.conf", old_override)
        except BaseException:
            replace_link(current, previous)
            if old_override is None:
                override.unlink(missing_ok=True)
            else:
                replace_file(override, old_override)
            run("systemctl", "--user", "daemon-reload")
            run("systemctl", "--user", "restart", SERVICE)
            raise


def rollback(root=RELEASE_ROOT, override=OVERRIDE):
    root = Path(root)
    current = root / "current"
    with (root / "activate.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not current.is_symlink():
            raise ValueError("no DEV release is active")
        active = current.readlink()
        active_override = override.read_bytes()
        previous = root / "previous"
        legacy = root / "legacy-service-override.conf"
        if previous.is_symlink():
            destination = previous.readlink()
            target = (root / destination).resolve()
            verify_release(target, target.name)
            replacement_override = active_override
        elif legacy.is_file():
            destination = None
            target = LEGACY_BUILD
            replacement_override = legacy.read_bytes()
        else:
            raise ValueError("no previous DEV release or legacy service is recorded")
        try:
            replace_link(current, destination)
            replace_file(override, replacement_override)
            run("systemctl", "--user", "daemon-reload")
            run("systemctl", "--user", "restart", SERVICE)
            if not serving_revision(target):
                raise RuntimeError("previous DEV game service did not become ready")
        except BaseException:
            replace_link(current, active)
            replace_file(override, active_override)
            run("systemctl", "--user", "daemon-reload")
            run("systemctl", "--user", "restart", SERVICE)
            raise


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--status":
        current = RELEASE_ROOT / "current"
        if current.is_symlink() and current.resolve().is_relative_to(RELEASE_ROOT / "releases"):
            try:
                if check_serving(current.resolve()):
                    print(current.resolve().name)
            except (OSError, ValueError, subprocess.CalledProcessError, TimeoutError):
                pass
        return
    if len(sys.argv) == 2 and sys.argv[1] == "--rollback":
        rollback()
        print("DEV Pi restored the previous service")
        return
    if len(sys.argv) != 2:
        raise SystemExit("Usage: activate-dev-pi.py [--status|--rollback|REVISION]")
    activate(sys.argv[1])
    print("DEV Pi deployed:", sys.argv[1])


if __name__ == "__main__":
    main()
