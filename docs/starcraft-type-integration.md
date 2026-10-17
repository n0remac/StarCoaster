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
success. Version 2 finite wave groups accept registered spawnable ground Zerg
enemies. `park_defense.wave_tiers` selects the highest `from_wave` threshold
for each durable wave sequence; omit it to retain legacy `units_per_wave`
Zerglings. Every authored group is persisted with its unit type, request IDs,
placement attempts, and native actor IDs. Manual waves use the same sequence
without moving the automatic deadline. The legacy
`all_zerglings_eliminated` outcome field remains accepted, but finite-wave
victory waits for every living enemy wave actor to die. Restart recovery
accepts old type-less journals only for an unchanged Zergling-only definition;
a changed scenario hash or a queue entry with a different type or position
fails clearly instead of recreating another unit.

Hydralisk and Ultralisk declarations append unit orders 70 and 80 and G2
banks 7 and 8. The pinned StarCraft image table resolves them to
`unit/zerg/hydra.grp` (297 frames, 128×128) and `unit/zerg/ultra.grp`
(265 frames, 128×128). Their independently inspected attack and death banks
are in the declarations. Local extraction preserves the Ultralisk's 72×58
idle body compared with the Marine's 21×25 body; the renderer applies no
Marine-sized rescaling. OpenBW supplies unit dimensions, placement, pathing,
weapon range, damage, and attack timing. The Go zone filter only proposes
candidate centers; native placement rejection advances to another candidate.
The Hydralisk body attack animates, but its projectile is not drawn in
OpenRCT2 because no generic projectile effect renderer exists.

For a two-client mixed-combat visual audit, run
`scripts/project.sh record --scenario frontier-outpost --duration 110 --video-layout combined --mixed-zerg-camera`.
Add `--mixed-zerg-heavy-defense` for a second capture with enough test-only
Marines to show Hydralisk and Ultralisk death animations. The lighter capture
isolates native Hydralisk ranged and Ultralisk melee HP loss; the heavier
capture requires both new death states.

The option creates an ignored test-only park-defense fixture on Frontier's
existing park, with a short first-wave delay and two camera angles. It leaves
the packaged Frontier timing and mission rules intact. Inspect the resulting
`combined.mp4`, screenshots, logs, and `verification.json` under
`run-data/artifacts/`. The mixed verifier requires matching snapshots, all
three kinds together, attack and death states, and Marine and enemy HP loss.
The lighter fixture also requires isolated native 10-HP Hydralisk ranged and
20-HP Ultralisk melee damage samples. Its 2026-10-17 capture had 265 matching
two-client sequences with no mismatches; the damage samples were at sequences
200 and 229. The heavier capture had 584 matching sequences with no mismatches
and recorded death states for both Hydralisks and its Ultralisk. These
observations come from the locally licensed native engines; extracted art and
recordings remain outside Git.

Air movement, transport, siege and morph modes,
new spells or effect renderers, resource collection, non-Terran construction,
Zerg larva production, and multi-producer relationships need separate runtime
work. The declarations do not implement those mechanics.
