# StarCraft type integration

Each supported unit or building has one authoritative JSON declaration at
`bridge-protocol/entities/<id>.json`. Schema version 1 covers the conventional
ground units and Terran buildings already supported by StarCoaster. The two
`bridge-protocol/starcraft-*.json` catalogs and the Go, C++, JavaScript, and
protocol definitions are generated compatibility artifacts. Do not edit them.

```sh
# 1. Create bridge-protocol/entities/<id>.json
# 2. Generate all derived definitions
python3 scripts/generate-starcraft-types.py
# 3. Validate declarations and generated files without writing
python3 scripts/generate-starcraft-types.py --check
# 4. Build and test
scripts/project.sh build
scripts/project.sh test
```

`scripts/project.sh generate` delegates to the same generator. The regular
offline test command runs `--check` first. The generator reads sorted entity
files, rejects unknown fields and unsupported capabilities, and writes only
changed outputs. `--check` compares every derived file, including both catalogs,
and never writes. The integration tests use an isolated temporary project tree.

## Choose identity and ordering

- Use a stable lowercase underscore ID that matches the filename. Choose a
  compile-time `native_type` from the pinned BWAPI `UnitType.h`. Do not use a
  hero or turret type. The ID is the wire identity; the BWAPI type delegates
  costs, prerequisites, supply, training time, health, combat, and queues to
  OpenBW.
- Set `schema_version` to `1`, `kind` to `unit` or `building`, and assign a
  `registry_order` greater than the current maximum for that kind. Existing
  values are pinned. A new unit's `visual.g2_order` must exceed the current
  maximum visual bank order. It is independent of `registry_order` so adding
  units never shifts older sprite IDs.
- For units, declare `race`, `ownership`, `controllable`, `movement`,
  `spawnable`, `legacy_static_base`, and every supported command explicitly.
  New runtime units use `legacy_static_base: 0`. `spawnable` controls direct
  spawning; it does not control native production. Current movement support is
  `ground`. Only the existing move, attack, attack-move, hold, stop, and Medic
  heal commands are supported. Do not infer capabilities from race or producer.
- A produced unit declares one `produced_at` building ID. The producer must
  declare `conventional_training: true`. Building declarations never list
  products: generation groups units by producer and orders them by
  `registry_order`. Barracks produces Marine, Firebat, Medic; Factory produces
  Vulture and Goliath. Native BWAPI still decides whether training is available.

## Declare visuals and prepare local art

A unit's embedded `visual` includes its asset key, `g2_order`, native GRP
`source`, frame count or minimum frame count, canvas when applicable, stride,
animation banks or frames and ticks, health-bar offset, and bounds. Every unit
needs idle and death states. A deliberate fallback may name another state, as
Vulture walk does. Goliath demonstrates `attachments`: its turret has its own
image, GRP, animation banks, `above_body` layer, and `native_target` facing.
Firebat owns the existing `firebat_flame` effect through `owned_effects` and
references it by ID; its renderer behavior remains Firebat-specific. Shared
direction values are fixed by the generator.

A building declares a stable `object_id`, `display_name`, footprint, maximum
health, `conventional_training`, and complete embedded `visual`. Supported art
methods are `static` and the Barracks-specific `barracks_lights`. The visual
names a native image and source and output sizes; an optional preview size and
offset adjust the construction-menu thumbnail. Barracks also declares its
existing training-light `animation`. The construction menu enumerates the
generated catalog.

After generation, run `scripts/prepare-starcraft-sprites.py --unit <asset>`
with locally licensed StarCraft archives to prepare a unit's GRP frames.
`scripts/install-bridge-sprites.py` appends new G2 paths after established
Marine, Zergling, Firebat, Medic, Vulture, flame, Goliath, and health-bar IDs.
`scripts/generate-starcraft-visual-registry.py` builds the native paint table.
For a building, `scripts/install-starcraft-construction-object.py` assembles
the `.parkobj`. `scripts/project.sh start` performs local preparation during
its normal build path. `BRIDGE_SPRITE_SOURCE=alien-scout` remains an explicit
placeholder option for development. Keep extracted art, `.parkobj` files,
builds, and captures in ignored local directories; never commit them.

## Verification and limits

The regression fixture records baseline catalog semantics, generated source
bytes, and every existing G2 path index, including Goliath. Temporary-tree
tests add one Ghost declaration and one Starport declaration, then exercise
catalogs, language and protocol registries, production, placeholder sprites,
synthetic building art, invalid declarations, deterministic output, and a
read-only stale check. Use the relevant native checks before a graphical
capture. The existing two-client capture command is:

```sh
scripts/project.sh record --scenario mt-zergling --armory-goliath-probe --duration 180
```

Inspect the rendered frames and `verification.json` before claiming graphical
success. The current scenario format still has Marine reinforcement and
Zergling wave restrictions. Air movement, transport, siege and morph modes,
new spells or effect renderers, resource collection, non-Terran construction,
Zerg larva production, and multi-producer relationships need separate runtime
work. The declarations do not implement those mechanics.
