#!/usr/bin/env python3
"""Licensed graphical regression: native park windows and passive Marine selection.

Requires Xvfb, xdotool, scrot, built engines, and local RCT2/StarCraft data.
"""
import ctypes
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from scenario_package import build_native_map, ensure_park, resolve, session_environment  # noqa: E402


def main():
    plan = resolve("frontier-outpost")
    ensure_park(plan)
    run = ROOT / "run-data" / f"shared-viewport-live-{time.time_ns()}"
    for name in ("server", "client"):
        plugins = run / name / "plugin"
        plugins.mkdir(parents=True)
        (plugins / "shared-viewport-probe.js").write_bytes((ROOT / "tests/shared_viewport_probe.js").read_bytes())
    (run / "client/plugin/rts-bridge.js").write_bytes((ROOT / "openrct2-plugin/rts-bridge.js").read_bytes())
    scenario = json.loads(Path(plan["scenario"]).read_text())
    for wave in scenario["waves"]:
        wave["trigger"] = {"type": "elapsed_frames", "frames": 100000}
    scenario_path = run / "scenario.json"
    scenario_path.write_text(json.dumps(scenario))
    native_map = build_native_map(plan, run / "frontier.scm")
    env = session_environment(plan, {"BRIDGE_SCENARIO_CONFIG": str(scenario_path),
        "BRIDGE_MAP_FILE": str(native_map), "BRIDGE_DISABLE_ASSAULT_AI": "1",
        "BRIDGE_SPAWN_JOURNAL": str(run / "spawns.json"),
        "BRIDGE_SERVER_DATA_DIR": str(run / "server"), "BRIDGE_CLIENT_DATA_DIR": str(run / "client"),
        "BRIDGE_LAUNCH_CLIENT": "0", "OPENBW_LOCAL_PATH": str(run / "openbw.socket"),
        "DISPLAY": ":93", "SDL_AUDIODRIVER": "dummy", "LIBGL_ALWAYS_SOFTWARE": "1"})
    processes, logs, checks = [], [], {}
    window_id = None

    def start(name, args):
        log = (run / f"{name}.log").open("w")
        logs.append(log)
        process = subprocess.Popen(args, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        processes.append(process)
        return process

    def source():
        return (run / "client.log").read_text(errors="replace")

    def wait(predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = predicate()
            if result:
                return result
            if any(process.poll() is not None for process in processes):
                raise RuntimeError(f"engine/display stopped; see {run}")
            time.sleep(0.1)
        raise TimeoutError(f"graphical input check; see {run}")

    def mouse(*args):
        subprocess.run(["xdotool", *map(str, args)], env=env, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def report(key):
        previous = len(re.findall(r"PARK_INPUT_REPORT (\{[^\r\n]+\})", source()))
        mouse("key", "--clearmodifiers", "ctrl+shift+" + key)
        rows = wait(lambda: rows if len(rows := re.findall(r"PARK_INPUT_REPORT (\{[^\r\n]+\})", source())) > previous else None)
        return json.loads(rows[-1])

    def hover(point):
        mouse("mousemove", "--window", window_id, round(point["x"]), round(point["y"]))
        time.sleep(0.2)

    def cursor_image():
        class CursorImage(ctypes.Structure):
            _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short),
                        ("width", ctypes.c_ushort), ("height", ctypes.c_ushort),
                        ("xhot", ctypes.c_ushort), ("yhot", ctypes.c_ushort),
                        ("serial", ctypes.c_ulong), ("pixels", ctypes.POINTER(ctypes.c_ulong)),
                        ("atom", ctypes.c_ulong), ("name", ctypes.c_char_p)]
        x11, fixes = ctypes.CDLL("libX11.so.6"), ctypes.CDLL("libXfixes.so.3")
        x11.XOpenDisplay.argtypes, x11.XOpenDisplay.restype = [ctypes.c_char_p], ctypes.c_void_p
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x11.XFree.argtypes = [ctypes.c_void_p]
        fixes.XFixesGetCursorImage.argtypes = [ctypes.c_void_p]
        fixes.XFixesGetCursorImage.restype = ctypes.POINTER(CursorImage)
        display = x11.XOpenDisplay(env["DISPLAY"].encode())
        if not display:
            raise RuntimeError("cannot inspect test display cursor")
        image = None
        try:
            image = fixes.XFixesGetCursorImage(display)
            cursor = image.contents
            return cursor.width, cursor.height, tuple(cursor.pixels[:cursor.width * cursor.height])
        finally:
            if image:
                x11.XFree(image)
            x11.XCloseDisplay(display)

    def click(point):
        hover(point)
        mouse("click", "1")
        time.sleep(0.2)

    try:
        start("display", ["Xvfb", ":93", "-screen", "0", "1280x800x24", "-nolisten", "tcp"])
        start("session", [str(ROOT / "scripts/run-world-session.sh"), plan["park"]])
        wait(lambda: "WORLD_READY" in (run / "session.log").read_text(errors="replace"), 100)
        player = start("client", [str(ROOT / "build/openrct2/openrct2"), "join", "127.0.0.1", "--port=11753",
            f"--rct2-data-path={env['RCT2_DATA_DIR']}",
            f"--openrct2-data-path={ROOT / 'build/openrct2-stage/usr/local/share/openrct2'}",
            f"--user-data-path={run / 'client'}"])
        wait(lambda: "RTS Bridge apply tick=" in source(), 45)
        window_id = subprocess.check_output(["xdotool", "search", "--onlyvisible", "--pid", str(player.pid)],
                                            env=env, text=True, stderr=subprocess.DEVNULL).splitlines()[-1]
        mouse("mousemove", "1144", "112", "click", "1")  # dismiss join notification
        marine = report("1")
        checks["selection_is_passive"] = marine["tool"] is None
        hover(marine["point"])
        marine_cursor = cursor_image()
        click(marine["point"])
        wait(lambda: "RTS Bridge selected Marines=openbw:1000" in source())
        checks["marine_click_selects"] = True
        ride = report("2")
        hover(ride["point"])
        park_cursor = cursor_image()
        checks["ride_hover_restores_native_cursor"] = park_cursor != marine_cursor
        click(ride["point"])
        state = report("5")
        checks["ride_window_opens"] = 12 in state["windows"]
        subprocess.run(["scrot", "-z", "-o", str(run / "ride.png")], env=env, check=True)
        guest = report("3")
        hover(guest["point"])
        checks["guest_hover_uses_native_cursor"] = cursor_image() == park_cursor
        click(guest["point"])
        state = report("5")
        checks["guest_window_opens"] = 23 in state["windows"]
        subprocess.run(["scrot", "-z", "-o", str(run / "guest.png")], env=env, check=True)
        overlap = report("6")
        mouse("keydown", "Alt_L")
        try:
            click(overlap["point"])
        finally:
            mouse("keyup", "Alt_L")
        checks["alt_click_opens_guest_under_marine"] = 23 in report("5")["windows"]
        subprocess.run(["scrot", "-z", "-o", str(run / "overlap.png")], env=env, check=True)
        tool = report("4")
        click(tool["point"])
        state = report("5")
        checks["active_tool_keeps_click"] = state["toolClicks"] == 1 and state["tool"] == "viewportprobe.construction"
        mouse("key", "--clearmodifiers", "ctrl+shift+u")
        checks["selection_shortcut_cancels_tool"] = report("5")["tool"] is None
        before = source().count("RTS Bridge selected Marines=")
        marine = report("1")
        click(marine["point"])
        wait(lambda: source().count("RTS Bridge selected Marines=") > before)
        checks["marine_selects_after_park_and_tool"] = True
        mouse("mousemove", "--window", window_id,
              round(marine["point"]["x"] + 80), round(marine["point"]["y"] + 40), "click", "3")
        wait(lambda: "verb=unit.move accepted=1" in (run / "session.log").read_text(errors="replace"))
        checks["right_click_delivers_squad_order"] = True
        assert all(checks.values()), checks
    finally:
        (run / "verification.json").write_text(json.dumps({"checks": checks}, indent=2) + "\n")
        print(json.dumps({"run": str(run), "checks": checks}))
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in reversed(processes):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
