#!/usr/bin/env python3
"""Bind the generated Frontier Outpost manifest to the generic remote bridge plugin."""

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "run-data/park-assault"


def build_config() -> dict:
    fixture = json.loads((DATA / "fixture.json").read_text())
    bw_map = json.loads((DATA / "map/park-assault.json").read_text())
    hp = {proxy["target_id"]: proxy["max_hp"] for proxy in bw_map["proxies"]}
    if len(hp) != 3 or fixture["transform"] != bw_map["transform"]:
        raise ValueError("park and OpenBW fixture manifests disagree")
    return {"scenario": "park-assault", "map_id": "park-assault", "name": fixture["name"],
            "bounds": fixture["bounds"], "transform": fixture["transform"],
            "targets": [target | {"max_hp": hp[target["id"]]} for target in fixture["targets"]]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = build_config()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    source = (ROOT / "openrct2-plugin/rts-bridge.js").read_text()
    args.output.write_text("var STARCOASTER_SCENARIO_CONFIG = "
                           + json.dumps(config, separators=(",", ":")) + ";\n" + source)
    (DATA / "scenario-config.json").write_text(json.dumps(config, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
