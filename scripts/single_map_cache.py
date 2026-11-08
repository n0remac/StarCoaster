"""Validated, content-addressed preparation cache for one existing park at a time."""

import fcntl
import hashlib
import json
import os
import re
import shutil
import uuid
from contextlib import contextmanager, nullcontext
from pathlib import Path

from park_preparation import isolated_preflight, prepare_pipeline
from prepare_existing_defense import prepare
from scenario_package import ROOT, SUPPORTED_PARK_FORMATS, build_native_map, ensure_park


SCHEMA_VERSION = 3
EFFECTIVE_SETTINGS = {"preset": "existing-park-enemy-base-b1", "layout_policy_version": 2,
                      "initial_balances": {"minerals": 50, "gas": 0}, "mapping": {"rules": []}}
REPO_INPUTS = (
    "scripts/prepare_existing_defense.py", "scripts/scenario_package.py",
    "scripts/economy-layout.js", "scripts/stage-scenario-structures.py",
    "scripts/stage-scenario-structures.js",
    "scripts/park_preparation.py", "scripts/single_map_cache.py",
    "scripts/create-world-base-map.py", "scripts/starcraft_map_pack.py",
    "scripts/run-isolated-world-preflight.sh", "scripts/run-world-session.sh",
    "scripts/run-bwapi.sh", "scripts/run-openrct2-host.sh",
    "scripts/install-starcraft-construction-object.py",
    "openrct2-plugin/rts-bridge.js", "openrct2-plugin/park-operator-permissions.js",
    "bridge-protocol", "upstream/bwapi/bwapi/TestAIModule/maps/TestModule/testmap1.scm",
    "build/openrct2/openrct2-cli", "build/openrct2-stage/usr/local/share/openrct2",
    "build/world-bridge", "build/bwapi/bin/BWAPILauncher", "build/bwapi/lib",
    "build/bridge-module/BridgeAIModule.so",
)


class CacheInvalid(RuntimeError):
    pass


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(path):
    path = Path(path)
    if not path.exists() or path.is_symlink():
        raise RuntimeError(f"missing or unsafe cache dependency: {path}")
    if path.is_file():
        return sha256_file(path)
    if not path.is_dir():
        raise RuntimeError(f"unsupported cache dependency: {path}")
    digest = hashlib.sha256()
    for child in sorted(path.rglob("*")):
        if child.is_symlink():
            raise RuntimeError(f"symlink in cache dependency: {child}")
        if child.is_file():
            digest.update(str(child.relative_to(path)).encode() + b"\0")
            digest.update(bytes.fromhex(sha256_file(child)))
    return digest.hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def dependency_identity(cache_root=None, roots=None):
    """Hash dependencies once per changed file, including licensed asset trees.

    A browser New Game can run while Chromium holds several GiB of memory.
    Re-reading every RCT2 and StarCraft byte then made a verified cache hit
    take 400 seconds on the Pi. Size, inode, mtime and ctime qualify a saved
    content digest; a changed file is still hashed before it enters the key.
    """
    cache_root = Path(cache_root or ROOT / "run-data/map-cache")
    if roots is None:
        rct2 = Path(os.environ.get("RCT2_DATA_DIR", str(Path.home() / "games/rct2"))).resolve()
        starcraft = Path(os.environ.get("STARCRAFT_DATA_DIR", str(Path.home() / "games/starcraft"))).resolve()
        roots = {name: ROOT / name for name in REPO_INPUTS}
        roots.update({str(rct2 / name): rct2 / name for name in ("Data", "ObjData", "Landscapes")})
        roots[str(starcraft)] = starcraft
    locks = cache_root / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    index_path = cache_root / "dependency-hashes.json"
    with (locks / "dependency-hashes.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if index_path.is_symlink():
            raise RuntimeError("unsafe dependency digest index")
        try:
            stored = json.loads(index_path.read_text()) if index_path.is_file() else {}
            old = stored["files"] if stored.get("schema_version") == 1 else {}
            if not isinstance(old, dict):
                old = {}
        except (OSError, ValueError, KeyError, TypeError):
            old = {}
        updated = {}

        def file_digest(path):
            key = str(path.resolve())
            stat = path.stat()
            signature = [stat.st_dev, stat.st_ino, stat.st_size,
                         stat.st_mtime_ns, stat.st_ctime_ns]
            entry = old.get(key)
            if (isinstance(entry, dict) and entry.get("stat") == signature
                    and isinstance(entry.get("sha256"), str)
                    and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
                digest = entry["sha256"]
            else:
                digest = sha256_file(path)
                after = path.stat()
                if [after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns] != signature:
                    raise RuntimeError(f"cache dependency changed during hashing: {path}")
            updated[key] = {"stat": signature, "sha256": digest}
            return digest

        def tree_digest(path):
            path = Path(path)
            if not path.exists() or path.is_symlink():
                raise RuntimeError(f"missing or unsafe cache dependency: {path}")
            if path.is_file():
                return file_digest(path)
            if not path.is_dir():
                raise RuntimeError(f"unsupported cache dependency: {path}")
            digest = hashlib.sha256()
            for child in sorted(path.rglob("*")):
                if child.is_symlink():
                    raise RuntimeError(f"symlink in cache dependency: {child}")
                if child.is_file():
                    digest.update(str(child.relative_to(path)).encode() + b"\0")
                    digest.update(bytes.fromhex(file_digest(child)))
            return digest.hexdigest()

        result = {name: tree_digest(path) for name, path in sorted(roots.items())}
        if updated != old:
            temporary = cache_root / f".dependency-hashes-{uuid.uuid4().hex}.tmp"
            try:
                temporary.write_text(json.dumps({"schema_version": 1, "files": updated},
                                                sort_keys=True, separators=(",", ":")))
                os.replace(temporary, index_path)
            finally:
                temporary.unlink(missing_ok=True)
        return result


def key_inputs(source, dependencies):
    original = Path(source).expanduser().resolve(strict=True)
    if not original.is_file() or original.suffix.lower() not in SUPPORTED_PARK_FORMATS:
        raise ValueError("source must be a supported OpenRCT2 scenario or save")
    return {"schema_version": SCHEMA_VERSION, "source_path": str(original),
            "source_name": original.name, "source_sha256": sha256_file(original),
            "settings": EFFECTIVE_SETTINGS,
            "dependencies": dependencies()}


def package_files(source_name, scenario_id):
    suffix = Path(source_name).suffix.lower()
    return (f"source/{source_name}", f"save/{scenario_id}{suffix}",
            "scenario.json", "mapping.json", "package.json",
            f"map/{scenario_id}.scm", "preflight.json", "server/scenarios.idx")


class SingleMapCache:
    def __init__(self, root=ROOT / "run-data/map-cache", dependencies=None,
                 preflight=isolated_preflight):
        self.root = Path(root).resolve()
        if not self.root.is_relative_to((ROOT / "run-data").resolve()):
            raise ValueError("cache must be inside run-data")
        self.dependencies = dependencies if dependencies is not None else lambda: dependency_identity(self.root)
        self.preflight = preflight
        for name in ("packages", "building", "failed", "retired", "locks", "logs"):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def identity(self, source, timing=None):
        with timing.stage("cache_lookup") if timing else nullcontext():
            inputs = key_inputs(source, self.dependencies)
            key = canonical_hash(inputs)
            if timing:
                timing.cache_key = key
                timing.source_sha256 = inputs["source_sha256"]
            return key, inputs

    def package_path(self, key):
        return self.root / "packages" / key

    @contextmanager
    def key_lock(self, key, exclusive=False):
        # Readers hold a shared lock through validation and copying. A rebuild
        # cannot retire a package while any reader still uses its path.
        with (self.root / "locks" / f"{key}.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield

    def validate(self, path, key, inputs):
        manifest_path = path / "manifest.json"
        if path.is_symlink() or not manifest_path.is_file() or manifest_path.is_symlink():
            raise CacheInvalid("missing manifest; run map-cache build --rebuild")
        try:
            manifest = json.loads(manifest_path.read_text())
            if (manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("key") != key
                    or manifest.get("key_inputs") != inputs or manifest.get("state") != "ready"):
                raise CacheInvalid("incompatible cache manifest; run map-cache build --rebuild")
            scenario_id = manifest["scenario_id"]
            if not isinstance(scenario_id, str) or not re.fullmatch(r"[a-z0-9-]{1,64}", scenario_id):
                raise CacheInvalid("invalid scenario identity; run map-cache build --rebuild")
            expected = set(package_files(inputs["source_name"], scenario_id))
            if set(manifest["files"]) != expected:
                raise CacheInvalid("incomplete cache manifest; run map-cache build --rebuild")
            children = list(path.rglob("*"))
            if any(child.is_symlink() for child in children):
                raise CacheInvalid("symlink in cache package; run map-cache build --rebuild")
            actual = {str(file.relative_to(path)) for file in children if file.is_file()}
            if actual != expected | {"manifest.json"}:
                raise CacheInvalid("unexpected or missing cache files; run map-cache build --rebuild")
            for relative in expected:
                file = path / relative
                if file.is_symlink() or not file.is_file():
                    raise CacheInvalid(f"unsafe or missing cache file {relative}; run map-cache build --rebuild")
                entry = manifest["files"][relative]
                if file.stat().st_size != entry["size"] or sha256_file(file) != entry["sha256"]:
                    raise CacheInvalid(f"corrupt cache file {relative}; run map-cache build --rebuild")
            scenario = json.loads((path / "scenario.json").read_text())
            metadata = json.loads((path / "package.json").read_text())
            preflight = json.loads((path / "preflight.json").read_text())
            source_rel, park_rel = package_files(inputs["source_name"], scenario_id)[:2]
            semantic_hash = canonical_hash({k: v for k, v in scenario.items() if k != "park_file"})
            if (scenario.get("scenario_id") != scenario_id or scenario.get("park_file") != park_rel
                    or metadata.get("source") != source_rel or preflight.get("status") != "passed"
                    or preflight.get("key") != key or preflight.get("source_sha256") != inputs["source_sha256"]
                    or preflight.get("park_sha256") != manifest["files"][park_rel]["sha256"]
                    or preflight.get("native_map_sha256") != manifest["files"][f"map/{scenario_id}.scm"]["sha256"]
                    or preflight.get("scenario_semantics_sha256") != semantic_hash
                    or preflight.get("mapping_sha256") != manifest["files"]["mapping.json"]["sha256"]):
                raise CacheInvalid("cache metadata or preflight identity mismatch; run map-cache build --rebuild")
            return manifest
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
            raise CacheInvalid("invalid cache package; run map-cache build --rebuild") from error

    def status(self, source, timing=None):
        key, inputs = self.identity(source, timing)
        with self.key_lock(key):
            return self._status_locked(key, inputs, timing)

    def _status_locked(self, key, inputs, timing=None):
        path = self.package_path(key)
        if not path.exists():
            return {"status": "missing", "key": key, "package": str(path), "inputs": inputs}
        try:
            with timing.stage("cache_validation") if timing else nullcontext():
                manifest = self.validate(path, key, inputs)
            return {"status": "ready", "key": key, "package": str(path),
                    "inputs": inputs, "manifest": manifest}
        except CacheInvalid as error:
            return {"status": "invalid", "key": key, "package": str(path),
                    "inputs": inputs, "reason": str(error)}

    def build(self, source, rebuild=False, timing=None, repair_invalid=False):
        key, inputs = self.identity(source, timing)
        with self.key_lock(key, exclusive=True):
            # A waiting requester must not publish under an outdated source key.
            with timing.stage("cache_recheck") if timing else nullcontext():
                if key_inputs(source, self.dependencies) != inputs:
                    raise RuntimeError("source or dependencies changed while waiting; retry build")
            path = self.package_path(key)
            cache_outcome = "built" if not path.exists() else "rebuilt"
            if path.exists():
                try:
                    with timing.stage("cache_validation") if timing else nullcontext():
                        manifest = self.validate(path, key, inputs)
                    if not rebuild:
                        if timing:
                            timing.cache_outcome = "hit"
                        return manifest, True
                except CacheInvalid:
                    cache_outcome = "repaired"
                    if not (rebuild or repair_invalid):
                        raise
            generation = uuid.uuid4().hex
            if timing:
                timing.cache_build_generation = generation
                if not timing.generation:
                    timing.generation = generation
            temporary = self.root / "building" / f"{key}.{generation}"
            temporary.mkdir()
            try:
                with timing.stage("cache_build") if timing else nullcontext():
                    plan = prepare_pipeline(source, temporary, generation, prepare, ensure_park,
                                            build_native_map,
                                            lambda g, p: self.preflight(g, p, temporary), timing)
                    if plan["validated_source_sha256"] != inputs["source_sha256"]:
                        raise RuntimeError("staged source changed during preparation; retry build")
                    if sha256_file(source) != inputs["source_sha256"]:
                        raise RuntimeError("source changed during preparation; retry build")
                    if self.dependencies() != inputs["dependencies"]:
                        raise RuntimeError("cache dependencies changed during preparation; retry build")
                    scenario_id = plan["scenario_id"]
                    source_rel, park_rel = package_files(inputs["source_name"], scenario_id)[:2]
                    scenario = json.loads(Path(plan["scenario"]).read_text())
                    scenario["park_file"] = park_rel
                    Path(plan["scenario"]).write_text(json.dumps(scenario, indent=2) + "\n")
                    metadata = json.loads((temporary / "package.json").read_text())
                    metadata["source"] = source_rel
                    (temporary / "package.json").write_text(json.dumps(metadata, indent=2) + "\n")
                    preflight = {"status": "passed", "key": key,
                                 "generation": generation, "source_sha256": inputs["source_sha256"],
                                 "park_sha256": sha256_file(temporary / park_rel),
                                 "native_map_sha256": sha256_file(Path(plan["native_map"])),
                                 "scenario_semantics_sha256": canonical_hash(
                                     {k: v for k, v in scenario.items() if k != "park_file"}),
                                 "mapping_sha256": sha256_file(temporary / "mapping.json")}
                    (temporary / "preflight.json").write_text(json.dumps(preflight, indent=2) + "\n")
                    for directory in (temporary / "server", temporary / "client"):
                        if directory.exists():
                            shutil.rmtree(directory)
                    # The preflight uses the same licensed RCT2 installation and
                    # has already built OpenRCT2's scenario index. Carry it into
                    # the fresh host profile so graphical New Game startup does
                    # not parse the full stock catalog while Chromium is active.
                    # OpenRCT2 still validates the index against the directory
                    # scan and rebuilds it when source files or language change.
                    native_index = temporary / "sessions" / generation / "preflight/server/scenarios.idx"
                    if not native_index.is_file() or native_index.is_symlink():
                        raise RuntimeError("native preflight did not produce a scenario index")
                    cached_index = temporary / "server/scenarios.idx"
                    cached_index.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(native_index, cached_index)
                    # Keep both native and park-staging evidence outside the
                    # immutable package. The staging directory also contains
                    # licensed local objects and must never be published there.
                    evidence = self.root / "logs" / f"{key}.{generation}"
                    logs = temporary / "sessions"
                    if logs.exists():
                        os.replace(logs, evidence)
                    stage = temporary / "structure-stage"
                    if stage.exists():
                        evidence.mkdir(parents=True, exist_ok=True)
                        os.replace(stage, evidence / "structure-stage")
                    files = {relative: {"size": (temporary / relative).stat().st_size,
                                        "sha256": sha256_file(temporary / relative)}
                             for relative in package_files(inputs["source_name"], scenario_id)}
                    manifest = {"schema_version": SCHEMA_VERSION, "state": "ready", "key": key,
                                "key_inputs": inputs, "scenario_id": scenario_id, "files": files}
                    (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
                    self.validate(temporary, key, inputs)
                    for file in temporary.rglob("*"):
                        if file.is_file():
                            file.chmod(0o444)
                    if path.exists():
                        retired = self.root / "retired" / f"{key}.{generation}"
                        os.replace(path, retired)
                        try:
                            os.replace(temporary, path)
                        except OSError:
                            os.replace(retired, path)
                            raise
                    else:
                        os.replace(temporary, path)
                if timing:
                    timing.cache_outcome = cache_outcome
                return manifest, False
            except BaseException:
                if temporary.exists():
                    os.replace(temporary, self.root / "failed" / f"{key}.{generation}")
                raise

    def materialize(self, source, session_dir, timing=None):
        key, inputs = self.identity(source, timing)
        with self.key_lock(key):
            state = self._status_locked(key, inputs, timing)
            return self._materialize_locked(source, session_dir, state, timing)

    def _materialize_locked(self, source, session_dir, state, timing=None):
        if state["status"] != "ready":
            raise CacheInvalid(f"cache {state['status']}: {state.get('reason', 'run map-cache build first')}")
        destination = Path(session_dir).resolve()
        if (not destination.is_relative_to((ROOT / "run-data").resolve())
                or destination.is_relative_to(self.root)):
            raise ValueError("session directory must be outside the cache and inside run-data")
        if destination.exists():
            raise ValueError("session directory already exists; choose a fresh writable path")
        if sha256_file(source) != state["inputs"]["source_sha256"]:
            raise RuntimeError("source changed before materialization; retry")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.parent / f".{destination.name}.{uuid.uuid4().hex}.tmp"
        manifest = state["manifest"]
        scenario_id = manifest["scenario_id"]
        source_rel, park_rel = package_files(state["inputs"]["source_name"], scenario_id)[:2]
        try:
            with timing.stage("materialization") if timing else nullcontext():
                temporary.mkdir()
                for relative in manifest["files"]:
                    if relative == "preflight.json":
                        continue
                    source_file = Path(state["package"]) / relative
                    target = temporary / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source_file, target)
                    target.chmod(0o644)
                    if sha256_file(target) != manifest["files"][relative]["sha256"]:
                        raise CacheInvalid(f"cache changed during materialization: {relative}")
                scenario = json.loads((temporary / "scenario.json").read_text())
                scenario["park_file"] = str((destination / park_rel).relative_to(ROOT))
                (temporary / "scenario.json").write_text(json.dumps(scenario, indent=2) + "\n")
                metadata = json.loads((temporary / "package.json").read_text())
                metadata["source"] = str((destination / source_rel).relative_to(ROOT))
                (temporary / "package.json").write_text(json.dumps(metadata, indent=2) + "\n")
                (temporary / "cache-materialization.json").write_text(json.dumps(
                    {"schema_version": SCHEMA_VERSION, "key": state["key"],
                     "source_sha256": state["inputs"]["source_sha256"]}, indent=2) + "\n")
                (temporary / "server").mkdir(exist_ok=True)
                (temporary / "client").mkdir()
                os.replace(temporary, destination)
        except BaseException:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
        return {"scenario_id": scenario_id, "scenario": str(destination / "scenario.json"),
                "mapping": str(destination / "mapping.json"), "park": str(destination / park_rel),
                "fixture": None, "navigation": None, "generator": None, "layout": None,
                "source": str(destination / source_rel),
                "validated_source_sha256": state["inputs"]["source_sha256"],
                "native_map": str(destination / "map" / f"{scenario_id}.scm"),
                "spawn_journal": str(destination / "spawn-queue.json"),
                "server_data": str(destination / "server"),
                "client_data": str(destination / "client")}
