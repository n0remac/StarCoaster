"""Resolve and prepare the existing packaged scenarios for project CLI commands."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
from park_layout import load as load_layout


ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_PARK_FORMATS = frozenset({".park", ".sc6", ".sc4", ".sv6", ".sv4"})
GENERATOR_INPUTS = ("scripts/park-assault-generator.js", "scripts/create-park-assault.py",
                    "scripts/park_navigation.py", "scripts/park_layout.py")


def resolve(scenario_id: str) -> dict:
    if not re.fullmatch(r"[a-z0-9-]{1,64}", scenario_id):
        raise ValueError("invalid scenario ID (use 1–64 lowercase letters, digits, or hyphens)")
    package = ROOT / "scenarios" / scenario_id
    if not package.resolve().is_relative_to((ROOT / "scenarios").resolve()):
        raise ValueError("unsafe scenario package path")
    scenario_path = package / "scenario.json"
    mapping_path = package / "mapping.json"
    metadata_path = package / "package.json"
    if not all(path.is_file() for path in (scenario_path, mapping_path, metadata_path)):
        raise ValueError(f"missing scenario package: {scenario_id}")
    scenario = json.loads(scenario_path.read_text())
    metadata = json.loads(metadata_path.read_text())
    if scenario.get("scenario_id") != scenario_id:
        raise ValueError("incomplete or mismatched scenario package")

    def output_path(value, field, isolated=False):
        if not isinstance(value, str):
            raise ValueError(f"invalid package {field}")
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != "run-data":
            raise ValueError(f"{field} must be under run-data")
        target = ROOT / relative
        base = ROOT / "run-data" / scenario_id if isolated else ROOT / "run-data"
        if (not (ROOT / "run-data").resolve().is_relative_to(ROOT.resolve())
                or not target.resolve().is_relative_to((ROOT / "run-data").resolve())
                or not target.resolve().is_relative_to(base.resolve())):
            raise ValueError(f"unsafe {field} output location")
        return str(target)

    generator = metadata.get("generator")
    layout = None
    source = None
    if generator == "layout-v1":
        value = metadata.get("layout")
        if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
            raise ValueError("invalid layout path")
        layout = package / value
        if not layout.resolve().is_relative_to(package.resolve()) or not layout.is_file():
            raise ValueError("missing or unsafe layout file")
        load_layout(layout)
        command = ["python3", "scripts/create-park-assault.py", "--layout", str(layout), "--scenario-id", scenario_id]
    elif generator == "existing-park":
        value = metadata.get("source")
        expected = ROOT / "run-data" / scenario_id / "source"
        if (not isinstance(value, str) or Path(value).suffix.lower() not in SUPPORTED_PARK_FORMATS or
                Path(value).is_absolute() or ".." in Path(value).parts or
                Path(value).parts[:3] != ("run-data", scenario_id, "source")):
            raise ValueError("invalid existing park source path")
        source = ROOT / value
        if not source.resolve().is_relative_to(expected.resolve()) or not expected.resolve().is_relative_to((ROOT / "run-data").resolve()):
            raise ValueError("unsafe existing park source path")
        if not source.is_file():
            raise ValueError(f"missing existing park source: {source}")
        command = None
    elif isinstance(generator, list) and generator in (["scripts/create-park-assault.py", "--playable"],
                                                     ["scripts/create-park-assault.py", "--example-defense"]):
        command = ["python3", *generator]
    else:
        raise ValueError("unrecognized park generator")
    isolated = layout is not None or source is not None
    park = output_path(scenario.get("park_file"), "park_file", isolated)
    expected_suffix = source.suffix.lower() if source else ".park"
    if isolated and park != str(ROOT / "run-data" / scenario_id / "save" / f"{scenario_id}{expected_suffix}"):
        raise ValueError("isolated park output does not match package")
    fixture = output_path(metadata.get("fixture"), "fixture", isolated) if source is None else None
    navigation = output_path(metadata.get("navigation"), "navigation", isolated) if source is None else None
    if layout and (fixture != str(ROOT / "run-data" / scenario_id / "fixture.json") or
                   navigation != str(ROOT / "run-data" / scenario_id / "navigation-elements.json")):
        raise ValueError("layout export output does not match generator")
    if not isolated:
        legacy = {"--playable": ("frontier-outpost", "frontier-playable", "frontier-outpost-playable.park"),
                  "--example-defense": ("example-defense", "example-defense", "example-defense.park")}
        owner, directory, filename = legacy[generator[1]]
        expected = ROOT / "run-data" / directory
        if (scenario_id != owner or park != str(expected / "save" / filename)
                or fixture != str(expected / "fixture.json")
                or navigation != str(expected / "navigation-elements.json")):
            raise ValueError("legacy generator outputs do not belong to selected scenario")
    output = ROOT / "run-data/scenarios" / scenario_id
    return {"scenario_id": scenario_id, "scenario": str(scenario_path),
            "mapping": str(mapping_path), "park": park,
            "fixture": fixture, "navigation": navigation,
            "generator": command, "layout": str(layout) if layout else None,
            "source": str(source) if source else None,
            "native_map": str(output / "map" / f"{scenario_id}.scm"),
            "spawn_journal": str(output / "spawn-queue.json"),
            "server_data": str(output / "server"), "client_data": str(output / "client")}


def ensure_park(plan: dict, force: bool = False) -> None:
    if plan.get("source"):
        source, park = Path(plan["source"]), Path(plan["park"])
        if not source.is_file():
            raise RuntimeError(f"missing existing park source: {source}")
        if source.suffix.lower() == ".park":
            with source.open("rb") as stream:
                signature = stream.read(4)
            if signature != b"PARK":
                raise RuntimeError(f"invalid OpenRCT2 park source: {source}")
        scenario_path = Path(plan["scenario"])
        scenario = json.loads(scenario_path.read_text())
        inputs = [source, scenario_path]
        if scenario.get("initial_structures"):
            inputs += [ROOT / "scripts/stage-scenario-structures.py",
                       ROOT / "scripts/stage-scenario-structures.js",
                       ROOT / "bridge-protocol/starcraft-types.json"]
        if force or not park.is_file() or any(path.stat().st_mtime_ns > park.stat().st_mtime_ns for path in inputs):
            # Managed imports were inspected after copying into this private
            # source path. Reuse that exact validation when bytes are still
            # identical; a second fresh OpenRCT2 process can take longer than
            # the graphical client's entire startup on the Pi.
            validated_hash = plan.get("validated_source_sha256")
            current_hash = hashlib.sha256(source.read_bytes()).hexdigest() if validated_hash else None
            actual = tuple(scenario["park_size"]) if validated_hash and current_hash == validated_hash \
                else inspect_existing_park(source)
            expected = scenario.get("park_size")
            if actual[0] > 256 or actual[1] > 256:
                raise RuntimeError(f"existing park exceeds 256x256 native map: {actual[0]}x{actual[1]}")
            if list(actual) != expected:
                raise RuntimeError(f"existing park size {actual[0]}x{actual[1]} differs from scenario {expected}")
            park.parent.mkdir(parents=True, exist_ok=True)
            temporary = park.with_suffix(".park.tmp")
            if scenario.get("initial_structures"):
                subprocess.run(["python3", "scripts/stage-scenario-structures.py",
                                str(source), str(temporary), str(scenario_path)], cwd=ROOT, check=True)
            else:
                shutil.copy2(source, temporary)
            os.replace(temporary, park)
        return
    park, fixture, navigation = (Path(plan[key]) for key in ("park", "fixture", "navigation"))
    inputs = [ROOT / path for path in GENERATOR_INPUTS if (ROOT / path).exists()]
    if plan.get("layout"):
        inputs.append(Path(plan["layout"]))
    if force or any(not path.is_file() for path in (park, fixture, navigation)) or any(
            source.stat().st_mtime > min(path.stat().st_mtime for path in (park, fixture, navigation)) for source in inputs):
        subprocess.run(plan["generator"], cwd=ROOT, check=True)
    if any(not path.is_file() for path in (park, fixture, navigation)):
        raise RuntimeError(f"park generator did not produce the complete {plan['scenario_id']} package")


def inspect_existing_park(source: Path) -> tuple[int, int]:
    """Ask OpenRCT2 for the real map size; never infer it from park bytes."""
    executable = ROOT / "build/openrct2/openrct2-cli"
    data = ROOT / "build/openrct2-stage/usr/local/share/openrct2"
    rct2 = Path(os.environ.get("RCT2_DATA_DIR", str(Path.home() / "games/rct2")))
    if not executable.is_file() or not (data / "g2.dat").is_file() or not rct2.is_dir():
        raise RuntimeError("OpenRCT2 build and licensed RCT2 data are required to inspect an existing park")
    with tempfile.TemporaryDirectory(prefix="starcoaster-park-inspect-") as directory:
        user = Path(directory)
        (user / "plugin").mkdir()
        (user / "config.ini").write_text("[network]\nadvertise = false\n")
        (user / "plugin/inspect.js").write_text(
            'registerPlugin({name:"Park Size Inspector",version:"1.0",authors:["StarCoaster"],'
            'type:"local",licence:"MIT",targetApiVersion:124,minApiVersion:124,main:function(){'
            'var done=false;context.subscribe("interval.tick",function(){if(done)return;done=true;'
            'console.log("STARCOASTER_PARK_SIZE "+JSON.stringify([map.size.x,map.size.y]));});}});')
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        log = user / "openrct2.log"
        command = [str(executable), "host", str(source), "--headless", "--address=127.0.0.1",
                   f"--port={port}", f"--rct2-data-path={rct2}",
                   f"--openrct2-data-path={data}", f"--user-data-path={user}"]
        with log.open("w") as stream:
            process = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
            try:
                # A fresh headless profile builds OpenRCT2's object index. On
                # the Pi this can exceed 30 seconds while a graphical client
                # is loading, even for a small stock scenario.
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    output = log.read_text(errors="replace")
                    marker = "STARCOASTER_PARK_SIZE "
                    if marker in output:
                        result, _ = json.JSONDecoder().raw_decode(output.split(marker)[-1])
                        if (not isinstance(result, list) or len(result) != 2 or
                                any(type(value) is not int or value < 1 for value in result)):
                            raise RuntimeError("OpenRCT2 reported an invalid park size")
                        return result[0], result[1]
                    if process.poll() is not None:
                        raise RuntimeError(f"OpenRCT2 could not load existing park: {output[-1000:]}")
                    time.sleep(.1)
                raise RuntimeError("OpenRCT2 park inspection timed out: " + output[-1000:])
            finally:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def build_native_map(plan: dict, output_override=None) -> Path:
    output = Path(output_override or plan["native_map"])
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["python3", "scripts/create-world-base-map.py", "--scenario", plan["scenario"],
                    "--output", str(output)], cwd=ROOT, check=True)
    return output


def session_environment(plan: dict, overrides=None) -> dict:
    env = os.environ.copy()
    env.setdefault("RCT2_DATA_DIR", str(Path.home() / "games/rct2"))
    env.setdefault("STARCRAFT_DATA_DIR", str(Path.home() / "games/starcraft"))
    env["BRIDGE_MAP_FILE"] = plan["native_map"]
    env["BRIDGE_SCENARIO_CONFIG"] = plan["scenario"]
    env["BRIDGE_RULES_CONFIG"] = plan["mapping"]
    env["BRIDGE_SPAWN_JOURNAL"] = plan["spawn_journal"]
    env.setdefault("BRIDGE_SERVER_DATA_DIR", plan["server_data"])
    env.setdefault("BRIDGE_CLIENT_DATA_DIR", plan["client_data"])
    env.setdefault("BRIDGE_LAUNCH_CLIENT", "1" if env.get("DISPLAY") else "0")
    if overrides:
        env.update(overrides)
    return env
