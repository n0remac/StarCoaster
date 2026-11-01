"""Low overhead, append-only timing records for private park selections."""

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone


STAGES = ("source_resolution", "source_validation", "source_staging", "source_inspection",
          "package_staging", "park_preparation", "native_map_generation", "isolated_preflight",
          "prior_session_stop", "session_startup", "client_join", "cache_lookup",
          "cache_recheck", "cache_validation", "cache_build", "materialization")


class LoadTiming:
    def __init__(self, park, path, kind="selection"):
        self.park = park
        self.path = path
        self.kind = kind
        self.generation = ""
        self.cache_key = None
        self.cache_outcome = None
        self.cache_build_generation = None
        self.source_sha256 = None
        self.started = time.monotonic_ns()
        self.wall_time = datetime.now(timezone.utc).isoformat()
        self.stages = {name: {"status": "unavailable", "elapsed_ms": None} for name in STAGES}
        self._finished = False

    @contextmanager
    def stage(self, name):
        previous = self.stages[name]
        start = time.monotonic_ns()
        stage = {"status": "running", "start_ms": round((start - self.started) / 1e6, 3),
                 "elapsed_ms": None}
        self.stages[name] = stage
        try:
            yield
        except BaseException as error:
            stage["status"] = "failed"
            stage["error_type"] = type(error).__name__
            raise
        else:
            stage["status"] = "ok"
        finally:
            stage["elapsed_ms"] = round((time.monotonic_ns() - start) / 1e6, 3)
            if previous["elapsed_ms"] is not None:
                stage["elapsed_ms"] = round(stage["elapsed_ms"] + previous["elapsed_ms"], 3)
                stage["start_ms"] = previous["start_ms"]
                stage["count"] = previous.get("count", 1) + 1

    def skip(self, name, reason):
        if self.stages[name]["status"] == "unavailable":
            self.stages[name] = {"status": "skipped", "elapsed_ms": None, "reason": reason}

    def finish(self, outcome, error=None):
        if self._finished:
            return
        self._finished = True
        record = {"schema_version": 1, "record": "park_load", "started_at_utc": self.wall_time,
                  "kind": self.kind, "map": self.park, "generation": self.generation,
                  "cache_key": self.cache_key,
                  "cache_outcome": self.cache_outcome,
                  "cache_build_generation": self.cache_build_generation,
                  "source_sha256": self.source_sha256, "outcome": outcome,
                  "error_type": type(error).__name__ if error else None,
                  "error": str(error)[:240] if error else None,
                  "total_ms": round((time.monotonic_ns() - self.started) / 1e6, 3),
                  "stages": self.stages,
                  "client_join_note": "No authoritative graphical client join event is observed by the supervisor"}
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(descriptor, (json.dumps(record, separators=(",", ":")) + "\n").encode())
            finally:
                os.close(descriptor)
        except OSError as write_error:
            print("supervisor: could not record load timing: " + str(write_error), flush=True)
