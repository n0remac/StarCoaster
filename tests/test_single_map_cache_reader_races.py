"""Deterministic reader/rebuild coordination regressions."""

import os
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import prepare_existing_defense
import single_map_cache
from single_map_cache import SingleMapCache


class ReaderRebuildRaceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "run-data")
        self.root = Path(self.temporary.name)
        self.source = self.root / "Example.park"
        self.source.write_bytes(b"PARKrace source")
        self.map_builds = 0
        self.inspect = mock.patch.object(prepare_existing_defense, "inspect_existing_park", return_value=(64, 64))
        self.inspect.start()
        self.native = mock.patch.object(single_map_cache, "build_native_map", side_effect=self.build_native_map)
        self.native.start()
        self.cache = SingleMapCache(self.root / "cache", dependencies=lambda: {"fixture": "v1"},
                                    preflight=lambda generation, plan, runtime: None)
        self.manifest, _ = self.cache.build(self.source)
        self.package = self.cache.package_path(self.manifest["key"])

    def tearDown(self):
        self.native.stop()
        self.inspect.stop()
        self.temporary.cleanup()

    def build_native_map(self, plan):
        self.map_builds += 1
        output = Path(plan["native_map"])
        output.parent.mkdir(parents=True, exist_ok=True)
        # A same-key rebuild with different bytes makes mixed reads observable.
        output.write_bytes(f"native-map-{self.map_builds}".encode())

    def test_reader_during_replacement_gap_gets_complete_package(self):
        retired = threading.Event()
        publish = threading.Event()
        signals = queue.Queue()
        results = {}
        real_replace = os.replace
        real_flock = single_map_cache.fcntl.flock

        def gated_replace(source, destination):
            result = real_replace(source, destination)
            if Path(source) == self.package and Path(destination).parent == self.cache.root / "retired":
                retired.set()
                if not publish.wait(5):
                    raise AssertionError("replacement gate timed out")
            return result

        def watched_flock(file, operation):
            if threading.current_thread().name == "cache-reader" and operation & single_map_cache.fcntl.LOCK_SH:
                signals.put("reader_lock_attempt")
            return real_flock(file, operation)

        def rebuild():
            try:
                results["rebuild"] = self.cache.build(self.source, rebuild=True)
            except BaseException as error:
                results["rebuild_error"] = error

        def read():
            try:
                results["plan"] = self.cache.materialize(self.source, self.root / "reader-session")
            except BaseException as error:
                results["reader_error"] = error
            finally:
                signals.put("reader_done")

        with mock.patch.object(single_map_cache.os, "replace", side_effect=gated_replace), \
             mock.patch.object(single_map_cache.fcntl, "flock", side_effect=watched_flock):
            builder = threading.Thread(target=rebuild, name="cache-builder")
            reader = threading.Thread(target=read, name="cache-reader")
            builder.start()
            try:
                self.assertTrue(retired.wait(5), "builder did not reach the replacement gap")
                reader.start()
                # Old code reports a missing cache; fixed code attempts the
                # shared lock and waits for publication. Both are explicit events.
                self.assertIn(signals.get(timeout=5), ("reader_done", "reader_lock_attempt"))
            finally:
                publish.set()
                if reader.ident is not None:
                    reader.join(5)
                builder.join(5)
        self.assertFalse(builder.is_alive())
        self.assertFalse(reader.is_alive())
        self.assertNotIn("rebuild_error", results)
        self.assertNotIn("reader_error", results)
        self.assertTrue(Path(results["plan"]["native_map"]).is_file())

    def test_rebuild_during_materialization_waits_for_reader_copy(self):
        copy_started = threading.Event()
        resume_copy = threading.Event()
        replacement_started = threading.Event()
        results = {}
        real_copyfile = single_map_cache.shutil.copyfile
        real_replace = os.replace

        def gated_copyfile(source, destination, *args, **kwargs):
            result = real_copyfile(source, destination, *args, **kwargs)
            if (threading.current_thread().name == "cache-reader"
                    and not copy_started.is_set()):
                copy_started.set()
                if not resume_copy.wait(5):
                    raise AssertionError("materialization gate timed out")
            return result

        def watched_replace(source, destination):
            result = real_replace(source, destination)
            if Path(source) == self.package and Path(destination).parent == self.cache.root / "retired":
                replacement_started.set()
            return result

        def read():
            try:
                results["plan"] = self.cache.materialize(self.source, self.root / "reader-session")
            except BaseException as error:
                results["reader_error"] = error

        def rebuild():
            try:
                results["rebuild"] = self.cache.build(self.source, rebuild=True)
            except BaseException as error:
                results["rebuild_error"] = error

        with mock.patch.object(single_map_cache.shutil, "copyfile", side_effect=gated_copyfile), \
             mock.patch.object(single_map_cache.os, "replace", side_effect=watched_replace):
            reader = threading.Thread(target=read, name="cache-reader")
            builder = threading.Thread(target=rebuild, name="cache-builder")
            reader.start()
            try:
                self.assertTrue(copy_started.wait(5), "reader did not start copying")
                builder.start()
                # The old builder reaches retirement while the copy is held.
                # Under the fix it waits on the reader's lock; the bounded wait
                # only releases that protected path, not a sleep-created race.
                replacement_started.wait(1)
            finally:
                resume_copy.set()
                reader.join(5)
                if builder.ident is not None:
                    builder.join(5)
        self.assertFalse(reader.is_alive())
        self.assertFalse(builder.is_alive())
        self.assertNotIn("reader_error", results)
        self.assertNotIn("rebuild_error", results)
        self.assertEqual(Path(results["plan"]["native_map"]).read_bytes(), b"native-map-1")
        self.assertEqual(self.map_builds, 2)


if __name__ == "__main__":
    unittest.main()
