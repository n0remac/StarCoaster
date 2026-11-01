"""Cache integrity, invalidation, locking, and fresh materialization."""

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import prepare_existing_defense
import single_map_cache
from load_timing import LoadTiming
from single_map_cache import CacheInvalid, SingleMapCache, sha256_tree


class SingleMapCacheTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "run-data")
        self.base = Path(self.temporary.name)
        self.source = self.base / "Example.park"
        self.source.write_bytes(b"PARKinitial park")
        self.dependencies = {"generator": "v1", "engine": "v1"}
        self.calls = {"map": 0, "preflight": 0}
        self.inspect = mock.patch.object(prepare_existing_defense, "inspect_existing_park", return_value=(64, 64))
        self.inspect.start()
        self.native = mock.patch.object(single_map_cache, "build_native_map", side_effect=self.build_native_map)
        self.native.start()
        self.cache = SingleMapCache(self.base / "cache", dependencies=lambda: dict(self.dependencies),
                                    preflight=self.preflight)

    def tearDown(self):
        self.native.stop()
        self.inspect.stop()
        self.temporary.cleanup()

    def build_native_map(self, plan):
        self.calls["map"] += 1
        target = Path(plan["native_map"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"native-map:" + Path(plan["scenario"]).read_bytes())

    def preflight(self, generation, plan, runtime):
        self.calls["preflight"] += 1
        self.assertTrue(Path(plan["park"]).is_file())
        self.assertTrue(Path(plan["native_map"]).is_file())

    def test_build_reuse_and_two_independent_writable_sessions(self):
        timing = LoadTiming("Example.park", self.base / "timings.jsonl", "cache_build")
        manifest, reused = self.cache.build(self.source, timing=timing)
        timing.finish("prepared")
        self.assertFalse(reused)
        self.assertEqual(self.calls, {"map": 1, "preflight": 1})
        self.assertEqual(self.cache.status(self.source)["status"], "ready")
        second, reused = self.cache.build(self.source)
        self.assertTrue(reused)
        self.assertEqual(second["key"], manifest["key"])
        self.assertEqual(self.calls, {"map": 1, "preflight": 1})
        self.assertEqual(list((self.cache.root / "building").iterdir()), [])
        plan_a = self.cache.materialize(self.source, self.base / "session-a")
        plan_b = self.cache.materialize(self.source, self.base / "session-b")
        self.assertEqual(Path(plan_a["scenario"]).exists(), True)
        self.assertEqual(json.loads(Path(plan_a["scenario"]).read_text())["park_file"],
                         str(Path(plan_a["park"]).relative_to(ROOT)))
        self.assertEqual(json.loads(Path(plan_b["scenario"]).read_text())["park_file"],
                         str(Path(plan_b["park"]).relative_to(ROOT)))
        for field in ("park", "native_map", "source", "scenario", "mapping", "server_data", "client_data"):
            self.assertNotEqual(plan_a[field], plan_b[field])
        self.assertFalse(Path(plan_a["spawn_journal"]).exists())
        self.assertFalse(Path(plan_b["spawn_journal"]).exists())
        cache_park = self.cache.package_path(manifest["key"]) / f"save/{manifest['scenario_id']}.park"
        self.assertNotEqual(Path(plan_a["park"]).stat().st_ino, cache_park.stat().st_ino)
        Path(plan_a["park"]).write_bytes(b"PARKmodified session")
        self.assertEqual(Path(plan_b["park"]).read_bytes(), b"PARKinitial park")
        self.assertEqual(cache_park.read_bytes(), b"PARKinitial park")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.cache.materialize(self.source, self.base / "session-a")
        record = json.loads((self.base / "timings.jsonl").read_text())
        self.assertEqual(record["cache_key"], manifest["key"])
        self.assertEqual(record["stages"]["isolated_preflight"]["status"], "ok")
        self.assertEqual(record["stages"]["cache_build"]["status"], "ok")

    def test_source_bytes_settings_and_dependency_change_invalidate(self):
        first = self.cache.status(self.source)["key"]
        stamp = self.source.stat()
        self.source.write_bytes(b"PARKchanged park")
        os.utime(self.source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertEqual(self.source.stat().st_size, stamp.st_size)
        second = self.cache.status(self.source)["key"]
        self.assertNotEqual(first, second)
        self.dependencies["generator"] = "v2"
        third = self.cache.status(self.source)["key"]
        self.assertNotEqual(second, third)
        self.dependencies["engine"] = "v2"
        fourth = self.cache.status(self.source)["key"]
        self.assertNotEqual(third, fourth)
        with mock.patch.object(single_map_cache, "EFFECTIVE_SETTINGS", {"preset": "changed"}):
            self.assertNotEqual(fourth, self.cache.status(self.source)["key"])

    def test_dependency_file_bytes_override_preserved_size_and_timestamp(self):
        dependency = self.base / "generator.py"
        dependency.write_bytes(b"alpha")
        first = sha256_tree(dependency)
        stamp = dependency.stat()
        dependency.write_bytes(b"omega")
        os.utime(dependency, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertEqual(dependency.stat().st_size, stamp.st_size)
        self.assertNotEqual(first, sha256_tree(dependency))

    def test_corrupt_missing_and_incompatible_package_require_rebuild(self):
        manifest, _ = self.cache.build(self.source)
        package = self.cache.package_path(manifest["key"])
        native = package / f"map/{manifest['scenario_id']}.scm"
        native.chmod(0o644)
        native.write_bytes(b"corrupted")
        self.assertEqual(self.cache.status(self.source)["status"], "invalid")
        with self.assertRaisesRegex(CacheInvalid, "corrupt cache file"):
            self.cache.build(self.source)
        rebuilt, reused = self.cache.build(self.source, rebuild=True)
        self.assertFalse(reused)
        self.assertEqual(rebuilt["key"], manifest["key"])
        self.assertEqual(self.cache.status(self.source)["status"], "ready")
        self.assertEqual(self.calls, {"map": 2, "preflight": 2})
        self.assertEqual(len(list((self.cache.root / "retired").iterdir())), 1)
        native = self.cache.package_path(manifest["key"]) / f"map/{manifest['scenario_id']}.scm"
        native.unlink()
        self.assertEqual(self.cache.status(self.source)["status"], "invalid")
        with self.assertRaises(CacheInvalid):
            self.cache.materialize(self.source, self.base / "bad-session")
        self.assertFalse((self.base / "bad-session").exists())

    def test_incompatible_manifest_is_rejected_until_deliberate_rebuild(self):
        manifest, _ = self.cache.build(self.source)
        path = self.cache.package_path(manifest["key"]) / "manifest.json"
        path.chmod(0o644)
        changed = json.loads(path.read_text())
        changed["schema_version"] += 1
        path.write_text(json.dumps(changed))
        self.assertEqual(self.cache.status(self.source)["status"], "invalid")
        with self.assertRaisesRegex(CacheInvalid, "incompatible"):
            self.cache.build(self.source)
        rebuilt, reused = self.cache.build(self.source, rebuild=True)
        self.assertFalse(reused)
        self.assertEqual(rebuilt["key"], manifest["key"])
        self.assertEqual(self.cache.status(self.source)["status"], "ready")

    def test_failed_preflight_and_changed_source_never_publish(self):
        def failed(generation, plan, runtime):
            raise RuntimeError("preflight failed")
        self.cache.preflight = failed
        with self.assertRaisesRegex(RuntimeError, "preflight failed"):
            self.cache.build(self.source)
        self.assertEqual(self.cache.status(self.source)["status"], "missing")
        self.assertEqual(len(list((self.cache.root / "failed").iterdir())), 1)
        self.cache.preflight = self.preflight
        manifest, _ = self.cache.build(self.source)
        self.assertEqual(self.cache.status(self.source)["status"], "ready")
        self.source.write_bytes(b"PARKother contents")
        self.assertNotEqual(self.cache.status(self.source)["key"], manifest["key"])
        def changed(generation, plan, runtime):
            self.source.write_bytes(b"PARKchanged again")
        self.cache.preflight = changed
        with self.assertRaisesRegex(RuntimeError, "source changed"):
            self.cache.build(self.source)
        self.assertEqual(self.cache.status(self.source)["status"], "missing")

    def test_dependency_change_during_build_never_publishes_old_key(self):
        old_key = self.cache.status(self.source)["key"]
        def changed(generation, plan, runtime):
            self.dependencies["engine"] = "new binary"
        self.cache.preflight = changed
        with self.assertRaisesRegex(RuntimeError, "dependencies changed"):
            self.cache.build(self.source)
        self.assertFalse(self.cache.package_path(old_key).exists())

    def test_concurrent_same_key_request_waits_and_reuses(self):
        entered, release = threading.Event(), threading.Event()
        results, errors = [], []
        def slow(generation, plan, runtime):
            self.calls["preflight"] += 1
            entered.set()
            if not release.wait(3):
                raise RuntimeError("test preflight wait timed out")
        self.cache.preflight = slow
        def worker():
            try:
                results.append(self.cache.build(self.source)[1])
            except Exception as error:
                errors.append(error)
        first = threading.Thread(target=worker)
        second = threading.Thread(target=worker)
        first.start()
        self.assertTrue(entered.wait(2))
        second.start()
        time.sleep(.05)
        self.assertTrue(second.is_alive())
        self.assertEqual(self.calls["preflight"], 1)
        release.set()
        first.join(4)
        second.join(4)
        self.assertFalse(errors, errors)
        self.assertCountEqual(results, [False, True])
        self.assertEqual(self.calls, {"map": 1, "preflight": 1})
        self.assertTrue(list((self.cache.root / "locks").iterdir()))

    def test_orphaned_build_and_persistent_lock_file_do_not_look_ready(self):
        key = self.cache.status(self.source)["key"]
        orphan = self.cache.root / "building" / f"{key}.orphan"
        orphan.mkdir()
        (orphan / "manifest.json").write_text('{"state":"ready"}')
        (self.cache.root / "locks" / f"{key}.lock").touch()
        self.assertEqual(self.cache.status(self.source)["status"], "missing")
        manifest, reused = self.cache.build(self.source)
        self.assertFalse(reused)
        self.assertEqual(manifest["key"], key)
        self.assertEqual(self.cache.status(self.source)["status"], "ready")


if __name__ == "__main__":
    unittest.main()
