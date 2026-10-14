"""Validate the intentionally small, data-only park layout format."""

import json
from pathlib import Path


RIDES = {
    "rct2.ride.fwh1": (265, 4, "Terran_Armory", 123, 750, 96, 55),
    "rct2.ride.mgr1": (266, 9, "Terran_Barracks", 111, 1000, 105, 73),
    "rct2.ride.burgb": (262, 1, "Terran_Missile_Turret", 124, 200, 33, 49),
    "rct2.ride.drnks": (262, 1, "Terran_Missile_Turret", 124, 200, 33, 49),
}
WALLS = {"rct2.scenery_wall.wpf", "rct2.scenery_wall.wbr1", "rct2.scenery_wall.wbr2"}
SMALL = {"rct2.scenery_small." + name for name in
         ("tap", "tco", "tbr", "tcf", "tf1", "tf2", "tg1", "tg2", "tg3", "tg4", "tg5")}
LARGE = {"rct2.scenery_large.sip", "rct2.scenery_large.ssig4"}


def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise ValueError(f"invalid park layout: {error}") from error
    if not isinstance(data, dict) or set(data) != {"version", "name", "size", "rides", "paths", "walls", "scenery", "large_scenery"}:
        raise ValueError("invalid park layout fields")
    if data["version"] != 1 or not isinstance(data["name"], str) or not 1 <= len(data["name"]) <= 64:
        raise ValueError("invalid park layout version or name")
    if data["size"] != [64, 64]:
        raise ValueError("layout-v1 requires a 64x64 park")
    for field in ("rides", "paths", "walls", "scenery", "large_scenery"):
        if not isinstance(data[field], list):
            raise ValueError(f"invalid {field}")

    def point(x, y):
        if type(x) is not int or type(y) is not int or not (8 <= x <= 55 and 8 <= y <= 55):
            raise ValueError(f"layout coordinate outside buildable area: {x},{y}")

    names, ids = set(), set()
    for ride in data["rides"]:
        if not isinstance(ride, dict) or set(ride) != {"id", "name", "object", "x", "y"}:
            raise ValueError("invalid ride placement")
        point(ride["x"], ride["y"])
        if ride["object"] not in RIDES or not isinstance(ride["name"], str) or not ride["name"] or not isinstance(ride["id"], str) or not ride["id"]:
            raise ValueError("unsupported ride")
        if ride["name"] in names or ride["id"] in ids:
            raise ValueError("duplicate ride identity")
        names.add(ride["name"]); ids.add(ride["id"])
        track, count, proxy, unit, hp, width, height = RIDES[ride["object"]]
        ride.update(track=track, expected=count, proxy_type=proxy, proxy_unit_type=unit,
                    proxy_hp=hp, collision={"width": width, "height": height})
    if not data["rides"]:
        raise ValueError("layout needs a ride")
    for path in data["paths"]:
        if not isinstance(path, dict) or path.get("kind") not in ("horizontal", "vertical", "plaza"):
            raise ValueError("invalid path primitive")
        kind = path["kind"]
        required = {"kind", "y", "x0", "x1"} if kind == "horizontal" else {"kind", "x", "y0", "y1"} if kind == "vertical" else {"kind", "x0", "y0", "x1", "y1"}
        if set(path) != required:
            raise ValueError("invalid path fields")
        x0, x1 = (path["x"], path["x"]) if kind == "vertical" else (path["x0"], path["x1"])
        y0, y1 = (path["y"], path["y"]) if kind == "horizontal" else (path["y0"], path["y1"])
        point(x0, y0); point(x1, y1)
        if x0 > x1 or y0 > y1:
            raise ValueError("reversed path segment")
    for wall in data["walls"]:
        if not isinstance(wall, dict) or set(wall) != {"x0", "y0", "x1", "y1", "direction", "object"}:
            raise ValueError("invalid wall segment")
        point(wall["x0"], wall["y0"]); point(wall["x1"], wall["y1"])
        if wall["x0"] > wall["x1"] or wall["y0"] > wall["y1"] or (wall["x0"] != wall["x1"] and wall["y0"] != wall["y1"]):
            raise ValueError("wall must be horizontal or vertical")
        if type(wall["direction"]) is not int or wall["direction"] not in range(4) or wall["object"] not in WALLS:
            raise ValueError("invalid wall edge or object")
    for field, allowed in (("scenery", SMALL), ("large_scenery", LARGE)):
        for item in data[field]:
            if not isinstance(item, dict) or set(item) != {"x", "y", "object"}:
                raise ValueError(f"invalid {field} placement")
            point(item["x"], item["y"])
            if item["object"] not in allowed:
                raise ValueError(f"unsupported {field} object")
    return data
