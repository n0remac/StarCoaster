#!/usr/bin/env python3
"""Generate compatibility catalogs and consumers from single-file entity declarations."""

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
ENTITIES = "bridge-protocol/entities"
BEGIN = "BEGIN GENERATED STARCRAFT TYPES"
END = "END GENERATED STARCRAFT TYPES"
COMMANDS = {"unit.move", "unit.attack", "unit.attack_move", "unit.hold", "unit.stop", "unit.heal"}
BASE_COMMANDS = {"unit.move", "unit.hold", "unit.stop"}
TYPE_ID = re.compile(r"[a-z][a-z0-9_]+")
OBJECT_ID = re.compile(r"starcoaster\.scenery_large\.[a-z][a-z0-9_]+")
PINNED_UNITS = {"terran_marine": (10, 2), "terran_firebat": (20, 3),
                "terran_medic": (30, 4), "terran_vulture": (40, 5),
                "terran_goliath": (50, 6), "zerg_zergling": (60, 1)}
PINNED_BUILDINGS = {"terran_barracks": 10, "terran_academy": 20,
                    "terran_supply_depot": 30, "terran_factory": 40,
                    "terran_armory": 50}
DIRECTIONS = {"east": [8, False], "southeast": [12, False],
              "south": [16, False], "southwest": [12, True],
              "west": [8, True], "northwest": [4, True],
              "north": [0, False], "northeast": [4, False]}
COMMON = {"schema_version", "kind", "id", "registry_order", "native_type",
          "display_name", "visual"}
UNIT_FIELDS = COMMON | {"race", "ownership", "controllable", "movement",
                        "spawnable", "legacy_static_base", "commands", "produced_at",
                        "owned_effects"}
BUILDING_FIELDS = COMMON | {"object_id", "width", "height", "max_health",
                            "animation", "conventional_training"}
UNIT_VISUAL_FIELDS = {"asset", "g2_order", "source", "image", "canvas",
                      "frame_count", "minimum_frame_count", "stride", "animations",
                      "health_offset", "bounds", "attachments", "effect"}
BUILDING_VISUAL_FIELDS = {"image", "asset", "source_size", "frame_count",
                          "output_size", "preview_size", "preview_offset", "art_method"}
ANIMATION_FIELDS = {"banks", "frames", "ticks", "fallback", "source", "canvas",
                    "name_without_zero"}
ATTACHMENT_FIELDS = {"name", "image", "source", "canvas", "frame_count", "stride",
                     "facing", "layer", "animations"}
EFFECT_FIELDS = {"asset", "source", "canvas", "frame_count", "stride", "banks",
                 "ticks", "palette_remap"}
UNIT_CATALOG_KEYS = ("id", "native_type", "race", "ownership", "display_name",
                     "controllable", "movement", "spawnable", "legacy_static_base", "commands")
BUILDING_CATALOG_KEYS = ("id", "native_type", "object_id", "display_name",
                         "width", "height", "max_health")


def quoted(value):
    return json.dumps(value, ensure_ascii=True)


def native_names(root=ROOT):
    BWAPI_TYPES = root / "upstream/bwapi/bwapi/include/BWAPI/UnitType.h"
    if not BWAPI_TYPES.is_file():
        raise ValueError(f"Missing pinned BWAPI types: {BWAPI_TYPES}; fetch upstream sources first")
    return set(re.findall(r"constexpr UnitType\s+([A-Za-z0-9_]+)\{Enum::", BWAPI_TYPES.read_text()))


def validate_animation(profile, label, required_death=True):
    if (not isinstance(profile.get("source"), str) or not profile["source"].lower().endswith(".grp")
            or not isinstance(profile.get("asset"), str) or not TYPE_ID.fullmatch(profile["asset"])
            or not isinstance(profile.get("stride"), int) or profile["stride"] < 1
            or not isinstance(profile.get("frame_count", profile.get("minimum_frame_count")), int)
            or not isinstance(profile.get("canvas", [32, 32]), list)):
        raise ValueError(f"Invalid visual source: {label}")
    animations = profile.get("animations")
    if not isinstance(animations, dict) or "idle" not in animations or (required_death and "death" not in animations):
        raise ValueError(f"Missing required visual state: {label}")
    for state, animation in animations.items():
        if state not in {"idle", "walk", "attack", "heal", "death"} or not isinstance(animation, dict):
            raise ValueError(f"Unsupported visual state: {label}.{state}")
        if "fallback" in animation:
            if animation["fallback"] not in animations or "fallback" in animations[animation["fallback"]]:
                raise ValueError(f"Invalid visual fallback: {label}.{state}")
            continue
        frames = animation.get("banks", animation.get("frames"))
        if (not isinstance(frames, list) or not 1 <= len(frames) <= 10
                or any(not isinstance(frame, int) or frame < 0 for frame in frames)
                or not isinstance(animation.get("ticks"), int) or not 0 <= animation["ticks"] <= 120
                or ("banks" in animation and any(frame * profile["stride"] + 16 >=
                    profile.get("frame_count", profile.get("minimum_frame_count", 0)) for frame in frames)
                    and "source" not in animation)):
            raise ValueError(f"Invalid visual frames: {label}.{state}")
    for attachment in profile.get("attachments", []):
        if attachment.get("facing") not in {"body", "native_target"} or attachment.get("layer") != "above_body":
            raise ValueError(f"Unsupported visual attachment: {label}")
        validate_animation({**attachment, "asset": attachment["name"]},
                           label + "." + attachment["name"], required_death=False)


def validate(catalog, visuals=None, root=ROOT):
    visuals = visuals if visuals is not None else json.loads((root / "bridge-protocol/starcraft-visuals.json").read_text())
    names = native_names(root)
    units = {item["id"]: item for item in catalog["units"]}
    buildings = {item["id"]: item for item in catalog["buildings"]}
    if (len(units) != len(catalog["units"]) or len(buildings) != len(catalog["buildings"])
            or set(units) & set(buildings)):
        raise ValueError("Duplicate StarCraft type ID")
    objects = set()
    native_types = set()
    legacy_bases = set()
    visual_orders = set()
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
        profile = visuals["units"][item["visual"]]
        validate_animation(profile, item["id"])
        order = profile.get("g2_order")
        if not isinstance(order, int) or order < 1 or order in visual_orders:
            raise ValueError(f"Invalid or duplicate visual bank order: {item['id']}")
        visual_orders.add(order)
        if profile.get("effect") and profile["effect"] not in visuals.get("effects", {}):
            raise ValueError(f"Missing visual effect: {item['id']}")
    for item in catalog["buildings"]:
        if (not TYPE_ID.fullmatch(item["id"])
                or item.get("native_type") not in names or item["native_type"] in native_types
                or not item.get("display_name")
                or not OBJECT_ID.fullmatch(item.get("object_id", "")) or item["object_id"] in objects
                or item["width"] < 1 or item["height"] < 1
                or not 1 <= item.get("max_health", 0) <= 100000
                or item.get("visual") not in visuals.get("buildings", {})):
            raise ValueError(f"Invalid building definition: {item['id']}")
        art = visuals["buildings"][item["visual"]]
        if (art.get("art_method") not in {"static", "barracks_lights"}
                or not art.get("image") or not art.get("asset")
                or any(not isinstance(value, int) or value < 1 for key in ("source_size", "output_size")
                       for value in art.get(key, []))
                or not 1 <= art.get("frame_count", 0) <= 256):
            raise ValueError(f"Invalid building visual profile: {item['id']}")
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


def _fields(value, required, optional, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label}: expected object")
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing:
        raise ValueError(f"{label}.{sorted(missing)[0]}: missing required field")
    if unknown:
        raise ValueError(f"{label}.{sorted(unknown)[0]}: unknown field")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def load_entities(root=ROOT):
    directory = root / ENTITIES
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise ValueError(f"{directory}: no entity declarations")
    entities = []
    for path in paths:
        label = path.relative_to(root)
        try:
            entity = json.loads(path.read_text(), object_pairs_hook=_unique_pairs)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"{label}: {error}") from error
        if not isinstance(entity, dict):
            raise ValueError(f"{label}: expected object")
        if entity.get("id") != path.stem:
            raise ValueError(f"{label}: id: must match filename {path.stem!r}")
        entities.append((label, entity))
    return entities


def validate_entities(entities, root=ROOT):
    names = native_names(root)
    seen = {"id": set(), "native_type": set(), "object_id": set(), "asset": set(),
            "g2_order": set(), "effect": set(), "unit_order": set(), "building_order": set()}
    by_id = {}
    for path, entity in entities:
        label = str(path)
        kind = entity.get("kind")
        if kind not in ("unit", "building"):
            raise ValueError(f"{label}: kind: expected 'unit' or 'building'")
        _fields(entity, UNIT_FIELDS - {"produced_at", "owned_effects"} if kind == "unit"
                else BUILDING_FIELDS - {"animation"},
                {"produced_at", "owned_effects"} if kind == "unit" else {"animation"}, label)
        if type(entity["schema_version"]) is not int or entity["schema_version"] != 1:
            raise ValueError(f"{label}: schema_version: only version 1 is supported")
        ident = entity["id"]
        if not isinstance(ident, str) or not TYPE_ID.fullmatch(ident):
            raise ValueError(f"{label}: id: invalid stable identifier")
        for field in ("id", "native_type"):
            value = entity[field]
            if not isinstance(value, str):
                raise ValueError(f"{label}: {field}: expected string")
            if value in seen[field]:
                raise ValueError(f"{label}: {field}: duplicate {value!r}")
            seen[field].add(value)
        if entity["native_type"] not in names:
            raise ValueError(f"{label}: native_type: unknown pinned BWAPI type {entity['native_type']!r}")
        if not isinstance(entity["display_name"], str) or not entity["display_name"]:
            raise ValueError(f"{label}: display_name: expected nonempty string")
        order = entity["registry_order"]
        bucket = "unit_order" if kind == "unit" else "building_order"
        pinned = PINNED_UNITS if kind == "unit" else PINNED_BUILDINGS
        expected = pinned.get(ident)
        if type(order) is not int or order < 1 or order in seen[bucket]:
            raise ValueError(f"{label}: registry_order: invalid or duplicate order")
        if expected is not None and order != (expected[0] if kind == "unit" else expected):
            raise ValueError(f"{label}: registry_order: established order is immutable")
        if expected is None and order <= (60 if kind == "unit" else 50):
            raise ValueError(f"{label}: registry_order: new entities must append above established orders")
        seen[bucket].add(order)
        profile = entity["visual"]
        if kind == "unit":
            if entity["race"] not in {"terran", "zerg", "protoss"} or not entity["native_type"].lower().startswith(
                    entity["race"] + "_"):
                raise ValueError(f"{label}: race: unsupported native race")
            if entity["movement"] != "ground":
                raise ValueError(f"{label}: movement: only ground units are supported")
            if entity["ownership"] not in {"player", "enemy"}:
                raise ValueError(f"{label}: ownership: unsupported owner")
            if type(entity["spawnable"]) is not bool or type(entity["controllable"]) is not bool:
                raise ValueError(f"{label}: spawnable/controllable: explicit booleans required")
            if (not isinstance(entity["commands"], list) or any(not isinstance(c, str) for c in entity["commands"])
                    or len(entity["commands"]) != len(set(entity["commands"]))
                    or not set(entity["commands"]) <= COMMANDS
                    or (entity["controllable"] and
                        (entity["ownership"] != "player" or not BASE_COMMANDS <= set(entity["commands"])))
                    or (not entity["controllable"] and entity["commands"])
                    or ("unit.heal" in entity["commands"] and entity["native_type"] != "Terran_Medic")):
                raise ValueError(f"{label}: commands: unsupported command/capability combination")
            base = entity["legacy_static_base"]
            if type(base) is not int or base < 0 or (base and (base % 1000 or base >= 3000)):
                raise ValueError(f"{label}: legacy_static_base: invalid legacy actor base")
            if ident not in PINNED_UNITS and base != 0:
                raise ValueError(f"{label}: legacy_static_base: new runtime units must use 0")
            _fields(profile, {"asset", "g2_order", "source", "stride", "animations",
                              "health_offset", "bounds"}, UNIT_VISUAL_FIELDS -
                    {"asset", "g2_order", "source", "stride", "animations", "health_offset", "bounds"},
                    label + ".visual")
            for field in ("frame_count", "minimum_frame_count"):
                if field in profile and (type(profile[field]) is not int or profile[field] < 1):
                    raise ValueError(f"{label}: visual.{field}: expected positive integer")
            if ("frame_count" in profile) == ("minimum_frame_count" in profile):
                raise ValueError(f"{label}: visual.frame_count: specify exactly one frame count field")
            if ident not in PINNED_UNITS and "canvas" not in profile:
                raise ValueError(f"{label}: visual.canvas: required for new units")
            if profile["asset"] in seen["asset"]:
                raise ValueError(f"{label}: visual.asset: duplicate sprite asset {profile['asset']!r}")
            seen["asset"].add(profile["asset"])
            if "canvas" in profile and (not isinstance(profile["canvas"], list)
                                        or len(profile["canvas"]) != 2
                                        or any(type(v) is not int or v < 1 for v in profile["canvas"])):
                raise ValueError(f"{label}: visual.canvas: expected two positive integers")
            for field, count in (("health_offset", 2), ("bounds", 3)):
                if not isinstance(profile[field], list) or len(profile[field]) != count or any(
                        type(v) is not int for v in profile[field]):
                    raise ValueError(f"{label}: visual.{field}: expected {count} integers")
            visual_order = profile["g2_order"]
            if type(visual_order) is not int or visual_order < 1 or visual_order in seen["g2_order"]:
                raise ValueError(f"{label}: visual.g2_order: invalid or duplicate bank order")
            if ident in PINNED_UNITS and visual_order != PINNED_UNITS[ident][1]:
                raise ValueError(f"{label}: visual.g2_order: established bank order is immutable")
            if ident not in PINNED_UNITS and visual_order <= 6:
                raise ValueError(f"{label}: visual.g2_order: new banks must append above established banks")
            seen["g2_order"].add(visual_order)
            _validate_visual_unit(profile, label)
            effects = entity.get("owned_effects", {})
            if not isinstance(effects, dict):
                raise ValueError(f"{label}: owned_effects: expected object")
            for effect_id, effect in effects.items():
                if effect_id != "firebat_flame" or effect_id in seen["effect"]:
                    raise ValueError(f"{label}: owned_effects.{effect_id}: unsupported or duplicate effect ownership")
                _fields(effect, EFFECT_FIELDS, set(), label + ".owned_effects." + effect_id)
                if (effect.get("asset") != "flame" or effect.get("palette_remap") != "Tileset/Badlands/ofire.pcx"
                        or effect.get("source") != "unit/thingy/flamer.grp"
                        or effect.get("canvas") != [224, 224]
                        or effect.get("frame_count") != 221 or effect.get("stride") != 17
                        or effect.get("banks") != [0, 2, 4, 6, 8, 10, 12]
                        or effect.get("ticks") != 2):
                    raise ValueError(f"{label}: owned_effects.{effect_id}: unsupported effect definition")
                seen["effect"].add(effect_id)
            if "produced_at" in entity and (not isinstance(entity["produced_at"], str)
                                             or not TYPE_ID.fullmatch(entity["produced_at"])):
                raise ValueError(f"{label}: produced_at: expected one building ID")
        else:
            if not entity["native_type"].startswith(("Terran_", "Zerg_")):
                raise ValueError(f"{label}: native_type: unsupported building race")
            if entity["native_type"].startswith("Zerg_") and entity["conventional_training"]:
                raise ValueError(f"{label}: conventional_training: Zerg buildings are passive")
            for field in ("object_id",):
                value = entity[field]
                if not isinstance(value, str) or not OBJECT_ID.fullmatch(value) or value in seen[field]:
                    raise ValueError(f"{label}: {field}: invalid or duplicate scenery object ID")
                seen[field].add(value)
            for field in ("width", "height", "max_health"):
                if type(entity[field]) is not int or not 1 <= entity[field] <= (100000 if field == "max_health" else 16):
                    raise ValueError(f"{label}: {field}: invalid footprint or health")
            if type(entity["conventional_training"]) is not bool:
                raise ValueError(f"{label}: conventional_training: expected boolean")
            _fields(profile, {"image", "asset", "source_size", "frame_count", "output_size", "art_method"},
                    BUILDING_VISUAL_FIELDS - {"image", "asset", "source_size", "frame_count", "output_size", "art_method"},
                    label + ".visual")
            for field in ("source_size", "output_size", "preview_size"):
                if field in profile and (not isinstance(profile[field], list) or len(profile[field]) != 2
                                         or any(type(v) is not int or v < 1 for v in profile[field])):
                    raise ValueError(f"{label}: visual.{field}: expected two positive integers")
            if "preview_offset" in profile and (not isinstance(profile["preview_offset"], list)
                                               or len(profile["preview_offset"]) != 2
                                               or any(type(v) is not int for v in profile["preview_offset"])):
                raise ValueError(f"{label}: visual.preview_offset: expected two integers")
            if (profile["art_method"] not in {"static", "barracks_lights"}
                    or type(profile["frame_count"]) is not int or not 1 <= profile["frame_count"] <= 256):
                raise ValueError(f"{label}: visual.art_method: unsupported building art")
            if profile["art_method"] == "barracks_lights" and ident != "terran_barracks":
                raise ValueError(f"{label}: visual.art_method: training lights only support Barracks")
            if "animation" in entity:
                animation = entity["animation"]
                _fields(animation, {"trigger", "frames", "ticks_per_frame"}, set(), label + ".animation")
                if animation["trigger"] != "training" or not all(
                        type(animation[f]) is int and 1 <= animation[f] <= 120 for f in ("frames", "ticks_per_frame")):
                    raise ValueError(f"{label}: animation: unsupported training animation")
        by_id[ident] = entity
    for path, entity in entities:
        if entity["kind"] != "unit":
            continue
        producer = entity.get("produced_at")
        if producer:
            target = by_id.get(producer)
            if target is None or target["kind"] != "building":
                raise ValueError(f"{path}: produced_at: unknown building producer {producer!r}")
            if not target["conventional_training"]:
                raise ValueError(f"{path}: produced_at: producer {producer!r} does not support conventional training")
        effect = entity["visual"].get("effect")
        if effect and effect not in seen["effect"]:
            raise ValueError(f"{path}: visual.effect: unowned effect {effect!r}")
    return by_id


def _validate_visual_unit(profile, label):
    try:
        validate_animation(profile, label + ".visual")
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{label}: visual: {error}") from error
    for state, animation in profile["animations"].items():
        _fields(animation, {"fallback"} if "fallback" in animation else {"ticks"},
                ANIMATION_FIELDS - ({"fallback"} if "fallback" in animation else {"ticks"}),
                f"{label}.visual.animations.{state}")
        if "fallback" not in animation:
            if ("banks" in animation) == ("frames" in animation):
                raise ValueError(f"{label}: visual.animations.{state}: specify banks or frames")
            if "frames" in animation and "source" not in animation and max(animation["frames"]) >= profile.get(
                    "frame_count", profile.get("minimum_frame_count", 0)):
                raise ValueError(f"{label}: visual.animations.{state}: frame exceeds source count")
    names = set()
    for attachment in profile.get("attachments", []):
        _fields(attachment, ATTACHMENT_FIELDS, set(), label + ".visual.attachments")
        if attachment["name"] in names or not TYPE_ID.fullmatch(attachment["name"]):
            raise ValueError(f"{label}: visual.attachments.name: duplicate or invalid name")
        names.add(attachment["name"])
        for state, animation in attachment["animations"].items():
            _fields(animation, {"fallback"} if "fallback" in animation else {"ticks"},
                    ANIMATION_FIELDS - ({"fallback"} if "fallback" in animation else {"ticks"}),
                    f"{label}.visual.attachments.{attachment['name']}.animations.{state}")


def project_catalogs(entities, root=ROOT):
    validate_entities(entities, root)
    units = sorted((entity for _, entity in entities if entity["kind"] == "unit"),
                   key=lambda entity: entity["registry_order"])
    buildings = sorted((entity for _, entity in entities if entity["kind"] == "building"),
                       key=lambda entity: entity["registry_order"])
    production = {building["id"]: [] for building in buildings}
    for unit in units:
        if "produced_at" in unit:
            production[unit["produced_at"]].append(unit["id"])
    catalog = {"units": [], "buildings": []}
    visuals = {"directions": DIRECTIONS, "units": {}, "effects": {}, "buildings": {}}
    for unit in units:
        catalog["units"].append({key: unit[key] for key in UNIT_CATALOG_KEYS} | {"visual": unit["id"]})
        visuals["units"][unit["id"]] = unit["visual"]
        visuals["effects"].update(unit.get("owned_effects", {}))
    for building in buildings:
        catalog["buildings"].append({key: building[key] for key in BUILDING_CATALOG_KEYS}
                                    | {"visual": building["id"], "production": production[building["id"]]}
                                    | ({"animation": building["animation"]} if "animation" in building else {}))
        visuals["buildings"][building["id"]] = building["visual"]
    validate(catalog, visuals, root)
    return catalog, visuals


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


def check_native(catalog, root=ROOT):
    header = root / 'openbw-bwapi-module/src/WorldStarcraftTypes.h'
    replace_block(header, native_units(catalog), True,
                  'BEGIN GENERATED STARCRAFT UNITS', 'END GENERATED STARCRAFT UNITS')
    replace_block(header, native_buildings(catalog), True,
                  'BEGIN GENERATED STARCRAFT BUILDINGS', 'END GENERATED STARCRAFT BUILDINGS')


def schema_definitions(catalog, root=ROOT):
    all_units = [unit["id"] for unit in catalog["units"]]
    spawnable = [unit["id"] for unit in catalog["units"] if unit["spawnable"]]
    world_path = root / 'bridge-protocol/world.v1.schema.json'
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
    snapshot_path = root / 'bridge-protocol/scenario.snapshot.v3.schema.json'
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


def _render_block(original, rendered, begin=BEGIN, end_marker=END):
    start = original.index('\n', original.index(begin)) + 1
    end = original.rfind('\n', 0, original.index(end_marker))
    return original[:start] + rendered + original[end:]


def render_generated_outputs(root=ROOT):
    catalog, visuals = project_catalogs(load_entities(root), root)
    outputs = {
        root / 'bridge-protocol/starcraft-types.json': json.dumps(catalog, indent=2) + '\n',
        root / 'bridge-protocol/starcraft-visuals.json': json.dumps(visuals, indent=2) + '\n',
    }
    for path, rendered, begin, end in (
        (root / 'internal/world/starcraft_types.go', go_definitions(catalog), BEGIN, END),
        (root / 'openrct2-plugin/rts-bridge.js', javascript_definitions(catalog), BEGIN, END),
        (root / 'openbw-bwapi-module/src/WorldStarcraftTypes.h', native_units(catalog),
         'BEGIN GENERATED STARCRAFT UNITS', 'END GENERATED STARCRAFT UNITS'),
        (root / 'openbw-bwapi-module/src/WorldStarcraftTypes.h', native_buildings(catalog),
         'BEGIN GENERATED STARCRAFT BUILDINGS', 'END GENERATED STARCRAFT BUILDINGS'),
    ):
        outputs[path] = _render_block(outputs.get(path, path.read_text()), rendered, begin, end)
    outputs.update(schema_definitions(catalog, root))
    return outputs


def generate(root=ROOT, check=False):
    outputs = render_generated_outputs(root)
    stale = [path for path, expected in outputs.items()
             if not path.is_file() or path.read_text() != expected]
    if check and stale:
        names = ', '.join(str(path.relative_to(root)) for path in stale)
        raise ValueError(f"Generated StarCraft definitions are stale: {names}")
    for path in stale:
        path.write_text(outputs[path])
    return stale


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--root', type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        generate(args.root.resolve(), args.check)
    except (ValueError, OSError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == '__main__':
    main()
