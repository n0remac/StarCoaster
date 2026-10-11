#!/usr/bin/env python3
"""Render a labeled OpenBW battle trace over a captured OpenRCT2 park scene."""

import argparse
from bisect import bisect_right
from collections import defaultdict
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import re
import runpy
import shutil
import struct
import subprocess

from PIL import Image, ImageDraw, ImageFont

from squad_verification import project
from video_capture import probe_video
from artifact_runs import ArtifactRun


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG = ROOT / "run-data/battle-feasibility/video-source.log"
DEFAULT_BACKGROUND = ROOT / "run-data/final-render-demo/client-a-t20.png"
DEFAULT_OUT = ROOT / "run-data/battle-demo"
STATE = re.compile(
    r"\[battle\] state frame=(\d+) id=(\d+) owner=(\d+) kind=(\w+) hp=(\d+) max_hp=(\d+) "
    r"order=(\w+) cooldown=(\d+) target=(-?\d+) orderTarget=(-?\d+) attacking=([01]) "
    r"attackFrame=([01]) facing=(\d+) x=(\d+) y=(\d+)"
)
DEATH = re.compile(r"\[battle\] destroyed id=(\d+) owner=(\d+) kind=(\w+) frame=(\d+)")
OUTCOME = re.compile(r"\[battle\] outcome frame=(\d+) zerg_alive=(\d+) terran_alive=(\d+) result=(\w+)")
DAMAGE = re.compile(r"\[battle\] damage id=(\d+) owner=(\d+) kind=(\w+) from=(\d+) to=(\d+) frame=(\d+)")
DIRS = ("east", "southeast", "south", "southwest", "west", "northwest", "north", "northeast")
MARINE_DIRECTIONS = {"east": (8, False), "southeast": (12, False), "south": (16, False),
                     "southwest": (12, True), "west": (8, True), "northwest": (4, True),
                     "north": (0, False), "northeast": (4, False)}


def read_trace(path: Path):
    timeline = defaultdict(list)
    deaths = {}
    damage = []
    outcome = None
    for line in path.read_text().splitlines():
        if match := STATE.search(line):
            frame, ident, owner, kind, hp, max_hp, order, cooldown, target, order_target, attacking, attack_frame, facing, x, y = match.groups()
            timeline[int(ident)].append({"frame": int(frame), "id": int(ident), "owner": int(owner),
                                         "kind": kind, "hp": int(hp), "max_hp": int(max_hp),
                                         "order": order, "cooldown": int(cooldown), "target": int(target),
                                         "order_target": int(order_target), "attacking": bool(int(attacking)),
                                         "attack_frame": bool(int(attack_frame)), "facing": int(facing),
                                         "x": int(x), "y": int(y)})
        if match := DEATH.search(line):
            ident, _owner, _kind, frame = match.groups()
            deaths[int(ident)] = int(frame)
        if match := DAMAGE.search(line):
            damage.append({"id": int(match[1]), "kind": match[3], "from": int(match[4]),
                           "to": int(match[5]), "frame": int(match[6])})
        if match := OUTCOME.search(line):
            outcome = {"frame": int(match[1]), "zerg_alive": int(match[2]),
                       "terran_alive": int(match[3]), "result": match[4]}
    if len(timeline) != 12 or outcome is None or not deaths or not damage:
        raise ValueError("trace lacks a complete 12-unit battle")
    for states in timeline.values():
        states.sort(key=lambda state: state["frame"])
    return timeline, deaths, damage, outcome


def load_sprites(game_dir: Path, out: Path):
    helper = runpy.run_path(str(ROOT / "scripts/prepare-starcraft-sprites.py"))
    source = out / "source"
    source.mkdir(parents=True, exist_ok=True)
    marine_grp = source / "marine.grp"
    palette = source / "Badlands.wpe"
    archives = {}
    archives["marine"] = helper["extract"](game_dir, "unit/terran/marine.grp", marine_grp)
    archives["palette"] = helper["extract"](game_dir, "Tileset/Badlands.wpe", palette)
    grp_data, wpe_data = marine_grp.read_bytes(), palette.read_bytes()
    count, width, height = struct.unpack_from("<HHH", grp_data)
    if count != 229 or (width, height) != (64, 64):
        raise ValueError(f"unexpected Marine GRP: {count} frames, {width}x{height}")
    decode = helper["decode_grp"]
    marine = {}
    marine_indices = {}
    for animation, base in (("idle", 0), ("walk", 17), ("attack", 51)):
        for direction, (index, mirror) in MARINE_DIRECTIONS.items():
            frame_index = base + index
            image = decode(grp_data, wpe_data, frame_index)
            if mirror:
                image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            marine[animation, direction] = image.resize((128, 128), Image.Resampling.NEAREST)
            marine_indices[f"{animation}_{direction}"] = frame_index
    for index in range(221, 229):
        marine["death", index - 221] = decode(grp_data, wpe_data, index).resize((128, 128), Image.Resampling.NEAREST)

    zerg_dir = ROOT / "run-data/generated-assets/starcraft/zergling"
    manifest = json.loads((zerg_dir / "manifest.json").read_text())
    zerg = {}
    for name, metadata in manifest["frames"].items():
        motion, direction = name[:-4].rsplit("_", 1)
        if motion != "idle" and not motion.startswith("walk"):
            continue
        sprite = Image.open(zerg_dir / name).convert("RGBA")
        zerg[motion, direction] = (sprite.resize((sprite.width * 2, sprite.height * 2), Image.Resampling.NEAREST),
                                   2 * metadata["x"], 2 * metadata["y"])
    if len(zerg) < 88:
        raise ValueError("incomplete local Zergling sprite pack")
    return marine, zerg, {"marine_archive": archives["marine"], "palette_archive": archives["palette"],
                           "marine_grp_sha256": hashlib.sha256(grp_data).hexdigest(),
                           "zergling_grp_sha256": manifest["source_sha256"],
                           "marine_source_frames": marine_indices}


@lru_cache(maxsize=8)
def font(size: int):
    path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default()


def screen_direction(facing: int) -> str:
    """Project an OpenBW world-space heading into the park camera's eight views."""
    angle = facing * math.tau / 256
    world_dx, world_dy = math.cos(angle), math.sin(angle)
    screen_dx = 2 * (world_dy - world_dx)
    screen_dy = world_dx + world_dy
    octant = round(math.atan2(screen_dy, screen_dx) * 4 / math.pi) % 8
    return DIRS[octant]


def actor_image(state, marine, zerg, frame):
    direction = screen_direction(state["facing"])
    if state["kind"] == "terran_marine":
        animation = "attack" if state["attack_frame"] else "walk" if state["order"] not in ("PlayerGuard", "AttackUnit") else "idle"
        return marine[animation, direction], -64, -64
    motion = f"walk{(frame // 4 + state['id']) % 10}" if state["order"] not in ("PlayerGuard", "Stop") or state["attacking"] else "idle"
    return zerg[motion, direction]


def draw_frame(background, states, deaths, tick, outcome, marine, zerg, elapsed, duration):
    canvas = background.copy()
    overlay = Image.new("RGBA", canvas.size)
    draw = ImageDraw.Draw(overlay)
    alive = {"terran_marine": 0, "zerg_zergling": 0}
    shown = []
    state_tick = min(tick, outcome["frame"])
    for ident, history in states.items():
        frames = [state["frame"] for state in history]
        index = bisect_right(frames, state_tick) - 1
        if index < 0:
            index = 0
        state = history[index]
        death_frame = deaths.get(ident)
        if death_frame is not None and tick >= death_frame + 10:
            continue
        if death_frame is None or tick < death_frame:
            alive[state["kind"]] += 1
        z = 128 if state["x"] >= 576 and 448 <= state["y"] <= 544 else 112
        px, py = project(state["x"], state["y"], 0, z, 112)
        shown.append((px + py, ident, state, px, py, death_frame))
    for _depth, ident, state, px, py, death_frame in sorted(shown):
        if death_frame is not None and tick >= death_frame and state["kind"] == "terran_marine":
            image = marine["death", min(7, max(0, tick - death_frame))]
            dx, dy = -64, -64
        else:
            image, dx, dy = actor_image(state, marine, zerg, tick)
        if death_frame is not None and tick >= death_frame:
            image = image.copy()
            opacity = max(0, death_frame + 10 - tick) / 10
            image.putalpha(image.getchannel("A").point(lambda alpha: int(alpha * opacity)))
        overlay.alpha_composite(image, (int(px + dx), int(py + dy)))
        if death_frame is None or tick < death_frame:
            bar_width = 48
            x0, y0 = int(px - bar_width // 2), int(py - 71)
            draw.rectangle((x0 - 1, y0 - 1, x0 + bar_width + 1, y0 + 6), fill=(0, 0, 0, 190))
            colour = (100, 205, 105, 245) if state["kind"] == "terran_marine" else (189, 100, 211, 245)
            draw.rectangle((x0, y0, x0 + int(bar_width * state["hp"] / state["max_hp"]), y0 + 5), fill=colour)
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((210, 44, 1068, 100), 8, fill=(14, 19, 23, 225))
    draw.text((229, 49), "MARINE DEFENSE  ·  ZERGLING ASSAULT", font=font(20), fill=(246, 244, 233))
    draw.text((229, 76), "OpenBW combat replay composited over an OpenRCT2 park capture", font=font(13), fill=(199, 209, 212))
    draw.rounded_rectangle((306, 674, 975, 717), 6, fill=(14, 19, 23, 225))
    draw.text((326, 685), f"MARINES  {alive['terran_marine']}/4", font=font(16), fill=(128, 220, 139))
    draw.text((570, 685), f"ZERGLINGS  {alive['zerg_zergling']}/8", font=font(16), fill=(218, 130, 230))
    draw.text((820, 686), f"BW TICK {tick:03}", font=font(13), fill=(226, 230, 226))
    if elapsed > duration - 2.3:
        draw.rounded_rectangle((450, 581, 820, 631), 7, fill=(14, 19, 23, 225))
        draw.text((472, 594), f"OPENBW RESULT: {outcome['result'].upper()}", font=font(19), fill=(245, 226, 175))
    return canvas.convert("RGB")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--background", type=Path, default=DEFAULT_BACKGROUND)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--game-dir", type=Path, default=Path(os.environ.get("STARCRAFT_DATA_DIR", "/home/pi/games/starcraft")))
    args = parser.parse_args()
    artifact_run = ArtifactRun("battle-replay", "OpenBW battle trace replay",
                               args.output, config={"log": str(args.log), "background": str(args.background)})
    args.output = artifact_run.output
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        render(args)
    except BaseException as error:
        status = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
        artifact_run.finalize(status, f"{type(error).__name__}: {error}")
        raise
    else:
        artifact_run.finalize("passed")


def render(args) -> None:
    timeline, deaths, damage, outcome = read_trace(args.log)
    marine, zerg, assets = load_sprites(args.game_dir, args.output)
    background = Image.open(args.background).convert("RGB")
    if background.size != (1280, 800):
        raise ValueError("expected a 1280x800 OpenRCT2 background capture")
    fps = 10
    frame_ms = 42
    lead_seconds = 1.4
    tail_seconds = 2.5
    duration = lead_seconds + outcome["frame"] * frame_ms / 1000 + tail_seconds
    video_path = args.output / "combined.mp4"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", "1280x800", "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(video_path)]
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
    screenshots = {}
    try:
        for number in range(int(duration * fps) + 1):
            elapsed = number / fps
            tick = max(0, int((elapsed - lead_seconds) * 1000 / frame_ms))
            frame = draw_frame(background, timeline, deaths, tick, outcome, marine, zerg, elapsed, duration)
            if number in (15, 36, 58, int(duration * fps)):
                path = args.output / f"frame-{number:03}.png"
                frame.save(path)
                screenshots[str(number)] = path.name
            encoder.stdin.write(frame.tobytes())
    finally:
        encoder.stdin.close()
        result = encoder.wait()
    if result != 0:
        raise RuntimeError(f"ffmpeg exited with status {result}")
    metadata = probe_video(video_path, (1280, 800))
    if metadata["frame_count"] < 50:
        raise RuntimeError("battle recording is unexpectedly short")
    shutil.copyfile(args.log, args.output / "bwapi.log")
    shutil.copyfile(args.background, args.output / "park-background.png")
    (args.output / "video-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    summary = {"representation": "OpenBW trace replay composited over a captured OpenRCT2 park scene",
               "commit_sha": commit,
               "renderer_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "source_log": str(args.log), "source_log_sha256": hashlib.sha256(args.log.read_bytes()).hexdigest(),
               "background": str(args.background), "background_sha256": hashlib.sha256(args.background.read_bytes()).hexdigest(),
               "marine_count": sum(history[0]["kind"] == "terran_marine" for history in timeline.values()),
               "zergling_count": sum(history[0]["kind"] == "zerg_zergling" for history in timeline.values()),
               "damage_events": {kind: sum(item["kind"] == kind for item in damage)
                                 for kind in ("terran_marine", "zerg_zergling")},
               "casualties": {kind: sum(history[0]["kind"] == kind and ident in deaths
                                      for ident, history in timeline.items())
                              for kind in ("terran_marine", "zerg_zergling")},
               "outcome": outcome, "assets": assets, "video": metadata, "screenshots": screenshots}
    (args.output / "verification.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(video_path)
    print(json.dumps({"frames": metadata["frame_count"], "duration": metadata["duration_seconds"],
                      "damage_events": summary["damage_events"], "casualties": summary["casualties"]}))


if __name__ == "__main__":
    main()
