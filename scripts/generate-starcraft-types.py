#!/usr/bin/env python3
"""Generate Go, JavaScript, BWAPI, and wire types from the StarCraft catalog."""

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "bridge-protocol/starcraft-types.json"
VISUALS = ROOT / "bridge-protocol/starcraft-visuals.json"
BWAPI_TYPES = ROOT / "upstream/bwapi/bwapi/include/BWAPI/UnitType.h"
BEGIN = "BEGIN GENERATED STARCRAFT TYPES"
END = "END GENERATED STARCRAFT TYPES"
COMMANDS = {"unit.move", "unit.attack", "unit.attack_move", "unit.hold", "unit.stop", "unit.heal"}
BASE_COMMANDS = {"unit.move", "unit.hold", "unit.stop"}
TYPE_ID = re.compile(r"[a-z][a-z0-9_]+")
OBJECT_ID = re.compile(r"starcoaster\.scenery_large\.[a-z][a-z0-9_]+")


def quoted(value):
    return json.dumps(value, ensure_ascii=True)


def native_names():
    if not BWAPI_TYPES.is_file():
        raise ValueError(f"Missing pinned BWAPI types: {BWAPI_TYPES}; fetch upstream sources first")
    return set(re.findall(r"constexpr UnitType\s+([A-Za-z0-9_]+)\{Enum::", BWAPI_TYPES.read_text()))


def validate(catalog, visuals=None):
    visuals = visuals if visuals is not None else json.loads(VISUALS.read_text())
    names = native_names()
    units = {item["id"]: item for item in catalog["units"]}
    buildings = {item["id"]: item for item in catalog["buildings"]}
    if (len(units) != len(catalog["units"]) or len(buildings) != len(catalog["buildings"])
            or set(units) & set(buildings)):
        raise ValueError("Duplicate StarCraft type ID")
    objects = set()
    native_types = set()
    legacy_bases = set()
    for item in catalog["units"]:
        if not TYPE_ID.fullmatch(item["id"]):
            raise ValueError("Invalid unit ID")
        if not all(item.get(key) for key in ("native_type", "race", "ownership", "display_name", "visual")):
            raise ValueError(f"Incomplete unit definition: {item['id']}")
        native = item["native_type"]
        if native not in names or native in native_types or native.startswith("Hero_") or native.endswith("_Turret"):
            raise ValueError(f"Unknown or duplicate native unit type: {native}")
        native_types.add(native)
        if item["race"] not in {"terran", "zerg", "protoss"} or not native.lower().startswith(item["race"] + "_"):
            raise ValueError(f"Invalid unit race: {item['id']}")
        if item["ownership"] not in {"player", "enemy"} or item.get("movement") != "ground":
            raise ValueError(f"Unsupported unit capability: {item['id']}")
        if not isinstance(item.get("controllable"), bool) or not isinstance(item.get("spawnable"), bool):
            raise ValueError(f"Invalid unit capability: {item['id']}")
        commands = item.get("commands")
        if (not isinstance(commands, list) or len(commands) != len(set(commands))
                or not set(commands) <= COMMANDS
                or (item["controllable"] and (item["ownership"] != "player" or not BASE_COMMANDS <= set(commands)))
                or (not item["controllable"] and commands)
                or ("unit.heal" in commands and native != "Terran_Medic")):
            raise ValueError(f"Unsupported unit commands: {item['id']}")
        base = item.get("legacy_static_base")
        if not isinstance(base, int) or base < 0 or (base and (base % 1000 or base >= 3000 or base in legacy_bases)):
            raise ValueError(f"Conflicting legacy actor identifier: {item['id']}")
        if base:
            legacy_bases.add(base)
        if item["visual"] not in visuals.get("units", {}):
            raise ValueError(f"Missing unit visual profile: {item['id']}")
    for item in catalog["buildings"]:
        if (not TYPE_ID.fullmatch(item["id"])
                or item.get("native_type") not in names or item["native_type"] in native_types
                or not item.get("display_name")
                or not OBJECT_ID.fullmatch(item.get("object_id", "")) or item["object_id"] in objects
                or item["width"] < 1 or item["height"] < 1
                or not 1 <= item.get("max_health", 0) <= 100000
                or item.get("visual") not in visuals.get("buildings", {})):
            raise ValueError(f"Invalid building definition: {item['id']}")
        native_types.add(item["native_type"])
        objects.add(item["object_id"])
        if any(unit not in units for unit in item["production"]):
            raise ValueError(f"Unsupported production type: {item['id']}")
        animation = item.get("animation")
        if animation is not None and (not isinstance(animation, dict)
                          or animation.get("trigger") != "training"
                          or not 1 <= animation.get("frames", 0) <= 32
                          or not 1 <= animation.get("ticks_per_frame", 0) <= 120):
            raise ValueError(f"Invalid building animation: {item['id']}")


def go_definitions(catalog):
    lines = ["var unitDefinitions = map[string]UnitDefinition{"]
    for unit in catalog["units"]:
        fields = [f'{key}: {quoted(unit[field])}' for key, field in (
            ("ID", "id"), ("NativeType", "native_type"), ("Race", "race"),
            ("Ownership", "ownership"), ("DisplayName", "display_name"), ("Visual", "visual"),
            ("Movement", "movement"))]
        fields.append(f'Controllable: {str(unit["controllable"]).lower()}')
        fields.append(f'Spawnable: {str(unit["spawnable"]).lower()}')
        fields.append(f'LegacyStaticBase: {unit["legacy_static_base"]}')
        fields.append('Commands: []string{' + ', '.join(map(quoted, unit["commands"])) + '}')
        lines.append(f'\t{quoted(unit["id"])}: {{' + ', '.join(fields) + '},')
    lines += ['}', '', 'var buildingDefinitions = map[string]BuildingDefinition{']
    for building in catalog["buildings"]:
        fields = [f'{key}: {quoted(building[field])}' for key, field in (
            ("ID", "id"), ("NativeType", "native_type"), ("ObjectID", "object_id"),
            ("DisplayName", "display_name"), ("Visual", "visual"))]
        fields += [f'Width: {building["width"]}', f'Height: {building["height"]}',
                   f'MaxHealth: {building["max_health"]}',
                   'Production: []string{' + ', '.join(map(quoted, building["production"])) + '}']
        lines.append(f'\t{quoted(building["id"])}: {{' + ', '.join(fields) + '},')
    return '\n'.join(lines + ['}']) + '\n'


def javascript_definitions(catalog):
    lines = ['    const UNIT_TYPES = Object.freeze({']
    for unit in catalog['units']:
        commands = [command.removeprefix('unit.') for command in unit['commands']]
        lines.append(f'        {unit["id"]}: {{ name: {quoted(unit["display_name"])}, '
                     f'visual: {quoted(unit["visual"])}, race: {quoted(unit["race"])}, '
                     f'controllable: {str(unit["controllable"]).lower()}, '
                     f'movement: {quoted(unit["movement"])}, spawnable: {str(unit["spawnable"]).lower()}, '
                     f'commands: {json.dumps(commands)} }},')
    lines += ['    });', '    const BUILDING_TYPES = Object.freeze({']
    for building in catalog['buildings']:
        lines.append(f'        {building["id"]}: {{ name: {quoted(building["display_name"])}, '
                     f'objectID: {quoted(building["object_id"])}, width: {building["width"]}, '
                     f'height: {building["height"]}, maxHealth: {building["max_health"]}, '
                     f'production: {json.dumps(building["production"])}, '
                     f'animation: {json.dumps(building.get("animation"), separators=(",", ":"))} }},')
    return '\n'.join(lines + ['    });'])


def replace_block(path, rendered, check, begin=BEGIN, end_marker=END):
    original = path.read_text()
    start = original.index('\n', original.index(begin)) + 1
    end = original.rfind('\n', 0, original.index(end_marker))
    updated = original[:start] + rendered + original[end:]
    if check and updated != original:
        raise ValueError(f"Generated StarCraft definitions are stale: {path}")
    if not check and updated != original:
        path.write_text(updated)


def native_units(catalog):
    lines = []
    for unit in catalog["units"]:
        lines.append(f'        {{{quoted(unit["id"])}, BWAPI::UnitTypes::{unit["native_type"]}, '
                     f'{quoted(unit["race"])}, {quoted(unit["ownership"])}, '
                     f'{str(unit["controllable"]).lower()}, {str(unit["spawnable"]).lower()}, '
                     f'{quoted(unit["visual"])}, {unit["legacy_static_base"]}}},')
    return '\n'.join(lines) + '\n'


def native_buildings(catalog):
    lines = []
    for building in catalog["buildings"]:
        production = ', '.join(map(quoted, building["production"]))
        lines.append(f'        {{{quoted(building["id"])}, BWAPI::UnitTypes::{building["native_type"]}, '
                     f'{quoted(building["object_id"])}, {building["width"]}, {building["height"]}, '
                     f'{quoted(building["display_name"])}, {str(bool(building["production"])).lower()}, '
                     f'{{{production}}}}},')
    return '\n'.join(lines) + '\n'


def check_native(catalog):
    header = ROOT / 'openbw-bwapi-module/src/WorldStarcraftTypes.h'
    replace_block(header, native_units(catalog), True,
                  'BEGIN GENERATED STARCRAFT UNITS', 'END GENERATED STARCRAFT UNITS')
    replace_block(header, native_buildings(catalog), True,
                  'BEGIN GENERATED STARCRAFT BUILDINGS', 'END GENERATED STARCRAFT BUILDINGS')


def schema_definitions(catalog):
    all_units = [unit["id"] for unit in catalog["units"]]
    spawnable = [unit["id"] for unit in catalog["units"] if unit["spawnable"]]
    world_path = ROOT / 'bridge-protocol/world.v1.schema.json'
    world_text = world_path.read_text()
    world = json.loads(world_text)
    for condition in world["allOf"]:
        if condition.get("if", {}).get("properties", {}).get("kind", {}).get("const") == "combat.command":
            previous_units = condition["then"]["properties"]["payload"]["properties"]["unit_type"]["enum"]
            break
    else:
        raise ValueError("Missing combat.command schema")
    defs = world["$defs"]
    if defs["actorIdentity"]["properties"]["type"]["enum"] != previous_units:
        raise ValueError("Protocol unit enumerations disagree")
    previous_spawn = defs["spawnRequest"]["properties"]["unit_type"]["enum"]
    if defs["spawnExecute"]["properties"]["unit_type"]["enum"] != previous_spawn:
        raise ValueError("Protocol spawn enumerations disagree")
    old, new = json.dumps(previous_units), json.dumps(all_units)
    if world_text.count(old) != 2:
        raise ValueError("Expected two protocol unit enumerations")
    world_text = world_text.replace(old, new)
    old, new = json.dumps(previous_spawn), json.dumps(spawnable)
    if world_text.count(old) != 2:
        raise ValueError("Expected two protocol spawn enumerations")
    world_text = world_text.replace(old, new)
    snapshot_path = ROOT / 'bridge-protocol/scenario.snapshot.v3.schema.json'
    snapshot_text = snapshot_path.read_text()
    snapshot = json.loads(snapshot_text)
    previous_snapshot = snapshot["properties"]["units"]["items"]["properties"]["kind"]["enum"]
    old, new = json.dumps(previous_snapshot), json.dumps(all_units)
    if snapshot_text.count(old) != 1:
        raise ValueError("Expected one combat snapshot unit enumeration")
    return {world_path: world_text, snapshot_path: snapshot_text.replace(old, new)}


def write_generated(path, rendered, check):
    if check and path.read_text() != rendered:
        raise ValueError(f"Generated StarCraft definitions are stale: {path}")
    if not check and path.read_text() != rendered:
        path.write_text(rendered)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    catalog = json.loads(CATALOG.read_text())
    validate(catalog)
    replace_block(ROOT / 'internal/world/starcraft_types.go', go_definitions(catalog), args.check)
    replace_block(ROOT / 'openrct2-plugin/rts-bridge.js', javascript_definitions(catalog), args.check)
    header = ROOT / 'openbw-bwapi-module/src/WorldStarcraftTypes.h'
    replace_block(header, native_units(catalog), args.check,
                  'BEGIN GENERATED STARCRAFT UNITS', 'END GENERATED STARCRAFT UNITS')
    replace_block(header, native_buildings(catalog), args.check,
                  'BEGIN GENERATED STARCRAFT BUILDINGS', 'END GENERATED STARCRAFT BUILDINGS')
    for path, rendered in schema_definitions(catalog).items():
        write_generated(path, rendered, args.check)


if __name__ == '__main__':
    main()
