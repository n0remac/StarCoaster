#!/usr/bin/env python3
"""Generate Go and plugin metadata from the supported StarCraft type catalog."""

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "bridge-protocol/starcraft-types.json"
BEGIN = "BEGIN GENERATED STARCRAFT TYPES"
END = "END GENERATED STARCRAFT TYPES"


def quoted(value):
    return json.dumps(value, ensure_ascii=True)


def validate(catalog):
    units = {item["id"]: item for item in catalog["units"]}
    buildings = {item["id"]: item for item in catalog["buildings"]}
    if len(units) != len(catalog["units"]) or len(buildings) != len(catalog["buildings"]):
        raise ValueError("Duplicate StarCraft type ID")
    objects = set()
    for item in catalog["units"]:
        if not re.fullmatch(r"[a-z][a-z0-9_]+", item["id"]):
            raise ValueError("Invalid unit ID")
        if not all(item[key] for key in ("native_type", "race", "ownership", "display_name", "visual")):
            raise ValueError(f"Incomplete unit definition: {item['id']}")
        if item["controllable"] and not item["commands"]:
            raise ValueError(f"Controllable unit has no orders: {item['id']}")
    for item in catalog["buildings"]:
        if (not re.fullmatch(r"[a-z][a-z0-9_]+", item["id"])
                or not item["native_type"] or not item["display_name"]
                or not item["object_id"] or item["object_id"] in objects
                or item["width"] < 1 or item["height"] < 1):
            raise ValueError(f"Invalid building definition: {item['id']}")
        objects.add(item["object_id"])
        if any(unit not in units for unit in item["production"]):
            raise ValueError(f"Unsupported production type: {item['id']}")


def go_definitions(catalog):
    lines = ["var unitDefinitions = map[string]UnitDefinition{"]
    for unit in catalog["units"]:
        fields = [f'{key}: {quoted(unit[field])}' for key, field in (
            ("ID", "id"), ("NativeType", "native_type"), ("Race", "race"),
            ("Ownership", "ownership"), ("DisplayName", "display_name"), ("Visual", "visual"))]
        fields.append(f'Controllable: {str(unit["controllable"]).lower()}')
        fields.append('Commands: []string{' + ', '.join(map(quoted, unit["commands"])) + '}')
        lines.append(f'\t{quoted(unit["id"])}: {{' + ', '.join(fields) + '},')
    lines += ['}', '', 'var buildingDefinitions = map[string]BuildingDefinition{']
    for building in catalog["buildings"]:
        fields = [f'{key}: {quoted(building[field])}' for key, field in (
            ("ID", "id"), ("NativeType", "native_type"), ("ObjectID", "object_id"),
            ("DisplayName", "display_name"), ("Visual", "visual"))]
        fields += [f'Width: {building["width"]}', f'Height: {building["height"]}',
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
                     f'commands: {json.dumps(commands)} }},')
    lines += ['    });', '    const BUILDING_TYPES = Object.freeze({']
    for building in catalog['buildings']:
        lines.append(f'        {building["id"]}: {{ name: {quoted(building["display_name"])}, '
                     f'objectID: {quoted(building["object_id"])}, width: {building["width"]}, '
                     f'height: {building["height"]}, production: {json.dumps(building["production"])}, '
                     f'animation: {quoted(building.get("animation", ""))} }},')
    return '\n'.join(lines + ['    });'])


def replace_block(path, rendered, check):
    original = path.read_text()
    start = original.index('\n', original.index(BEGIN)) + 1
    end = original.rfind('\n', 0, original.index(END))
    updated = original[:start] + rendered + original[end:]
    if check and updated != original:
        raise ValueError(f"Generated StarCraft definitions are stale: {path}")
    if not check and updated != original:
        path.write_text(updated)


def check_native(catalog):
    native = (ROOT / 'openbw-bwapi-module/src/WorldStarcraftTypes.h').read_text()
    for section in ('units', 'buildings'):
        for item in catalog[section]:
            pattern = re.escape('{' + quoted(item['id']) + ', BWAPI::UnitTypes::' + item['native_type'])
            if not re.search(pattern, native):
                raise ValueError(f"Native type resolution missing: {item['id']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    catalog = json.loads(CATALOG.read_text())
    validate(catalog)
    replace_block(ROOT / 'internal/world/starcraft_types.go', go_definitions(catalog), args.check)
    replace_block(ROOT / 'openrct2-plugin/rts-bridge.js', javascript_definitions(catalog), args.check)
    if args.check:
        check_native(catalog)


if __name__ == '__main__':
    main()
