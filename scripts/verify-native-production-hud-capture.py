#!/usr/bin/env python3
"""Verify the seven-building gallery and observed two-client Zerg morph."""

import json
import re
import sys
from pathlib import Path

from PIL import Image


LABELS = ("hatchery", "spawning-pool", "barracks", "academy",
          "supply-depot", "factory", "armory")
ACTOR = re.compile(r"openbw:(\d+),[^;\n]*?,(zerg_larva|zerg_egg|zerg_zergling),")
TERRAN_ACTOR = re.compile(r"openbw:(\d+),[^;\n]*?,(terran_marine|terran_vulture),")


def observed(log):
    kinds = {"zerg_larva": set(), "zerg_egg": set(), "zerg_zergling": set()}
    pairs = set()
    for line in log.splitlines():
        if "RTS Bridge apply tick=" not in line:
            continue
        actors = [(int(native), kind) for native, kind in ACTOR.findall(line)]
        for native, kind in actors:
            kinds[kind].add(native)
        lings = sorted(native for native, kind in actors if kind == "zerg_zergling")
        if len(lings) >= 2:
            pairs.add(tuple(lings[:2]))
    return kinds, pairs


def main(out):
    report_file = out / "verification.json"
    report = json.loads(report_file.read_text())
    server = (out / "server.log").read_text(errors="replace")
    client = [(out / f"client-{name}.log").read_text(errors="replace")
              for name in ("a", "b")]
    traces = [observed(log) for log in client]
    terran = [{kind: {int(native) for native, actor in TERRAN_ACTOR.findall(log)
                      if actor == kind} for kind in ("terran_marine", "terran_vulture")}
              for log in client]
    morph_ids = [kinds["zerg_egg"] & kinds["zerg_zergling"] for kinds, _ in traces]
    matching_morphs = set.intersection(*morph_ids)
    matching_pairs = traces[0][1] & traces[1][1]
    gallery = out / "building-hud-gallery"
    images = []
    for label in LABELS:
        path = gallery / f"{label}.png"
        if path.is_file():
            with Image.open(path) as image:
                if image.size == (1280, 800) and path.stat().st_size > 50_000:
                    images.append(label)
    checks = {
        "seven_building_gallery": len(images) == len(LABELS),
        "gallery_focus_sequence": all("NATIVE_HUD_FOCUS building=" + label in client[0]
            for label in ("Spawning Pool", "Barracks", "Academy", "Supply Depot", "Factory", "Armory")),
        "native_zerg_order_accepted": bool(re.search(
            r"native production command=.*unit_type=zerg_zergling accepted=1", server)),
        "barracks_ui_training_accepted": bool(re.search(
            r"\[world-control\] train command=.*accepted=1[^\n]*unit_type=terran_marine", server)),
        "factory_ui_training_accepted": bool(re.search(
            r"\[world-control\] train command=.*accepted=1[^\n]*unit_type=terran_vulture", server)),
        "client_order_submitted": bool(re.search(r"NATIVE_HUD_ORDER request=\d+ accepted=true", client[0])),
        "both_clients_saw_larvae": all(kinds["zerg_larva"] for kinds, _ in traces),
        "same_larva_became_egg_and_zergling": any(
            native in traces[0][0]["zerg_larva"] for native in matching_morphs),
        "both_clients_saw_same_egg_morph": bool(matching_morphs),
        "both_clients_saw_distinct_zergling_pair": any(
            any(native in pair for native in matching_morphs) for pair in matching_pairs),
        "training_gallery": all((gallery / f"{label}-training.png").is_file()
                                for label in ("barracks", "factory")),
        "both_clients_saw_trained_marine": bool(
            (terran[0]["terran_marine"] & terran[1]["terran_marine"])
            - set(range(1000, 1005))),
        "both_clients_saw_trained_vulture": bool(
            terran[0]["terran_vulture"] & terran[1]["terran_vulture"]),
    }
    report["native_production_hud"] = {
        "checks": checks, "gallery": [f"building-hud-gallery/{label}.png" for label in images],
        "morph_ids": sorted(matching_morphs),
        "zergling_pairs": [list(pair) for pair in sorted(matching_pairs)],
    }
    report["capture_complete"] = report["capture_complete"] and all(checks.values())
    report["status"] = "passed" if report["capture_complete"] else "incomplete"
    report_file.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["native_production_hud"], indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
