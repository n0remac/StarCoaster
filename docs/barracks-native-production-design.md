# Native Barracks and Marine production

## Confirmed engine behavior

The pinned OpenBW/BWAPI build supports a completed `Terran_Barracks` created
through `Game::createUnit` and a real `Unit::train(Terran_Marine)` queue. A
Marine costs 50 minerals and two half-supply units and takes 360 native frames.
OpenBW deducts resources, reserves supply, grows the incomplete trainee, and
releases it when training finishes. Both multiplayer participants perform the
same actions. The initial focused experiment is in
`run-data/barracks-native-completion-1792192837/server.log`.

Two small OpenBW patches are needed for a park building:

- `0005-editor-building-fog-openbw.patch` lets an editor-created building be
  placed outside the Terran player's explored tiles. Ordinary worker
  construction still checks exploration.
- `0006-native-production-egress-openbw.patch` lets a completed Marine search
  for a nearby exit without requiring reachability from the Barracks' blocked
  interior. Terrain walkability and unit collision still apply. Without it,
  OpenBW accepted training and spent 50 minerals but discarded the trainee at
  completion because the park navigation mask blocked the starting position.

Mt. Zergling has a scenario-owned production fixture: 500 Terran minerals and
one native Supply Depot at native tile (4, 4), outside its mapped park. Both
OpenBW participants receive the same initial minerals; OpenBW owns all later
resource and supply accounting. The fixture is not an OpenRCT2 object or a
player construction option.

## Authority and command flow

| State or action | Authority |
| --- | --- |
| Placement, scenery, save data, generation | OpenRCT2 |
| Ordered world revision and park/native ID link | Go bridge |
| Barracks HP, destruction, queue, resources, Marine creation | OpenBW |
| Construction and production UI, commander authorization | OpenRCT2 plugin |

A confirmed park Barracks is a `structure` with its own persistent scenery ID
and generation. After both participants apply its 4×3 navigation footprint,
the publisher creates one real Terran Barracks for the entity's owner and
reports its native ID and HP through `entity.state`. It first searches for an
existing owner/type/position match during recovery. There is no civilian proxy
for this structure and no second collision footprint. The controller links the
same park ID to the native unit. A bridge reconnect replays the target link;
it does not create another building.

The information window reads the native `building.state` report for HP, queue,
remaining frames, minerals, and supply. Clicking Train Marine uses the existing
synchronized OpenRCT2 command action with an empty `unit_ids`, verb
`unit.train`, and the persistent building ID as `target_id`. OpenRCT2 checks
that the submitting player is the current Terran commander and prevents a
second action with the same session/player/request ID. Go validates the current
structure and target link. The OpenBW controller checks the linked native ID,
owner, type, completion, and HP before calling `Unit::train`.

OpenBW emits a trainee creation event at the start of the queue. The actor
bridge waits for `Unit::isCompleted()` before publishing and binding it. Once
both participants bind it, the existing combat snapshot renders the Marine;
ordinary selection and movement commands work. `combat.result` reports command
acceptance, and `building.state` reports queue progress. The controller's
monotonic command serial prevents a resent native command from training or
charging twice in the same simulation session.

Demolition remains a normal OpenRCT2 scenery action and ordered `world.patch`.
The publisher retires the linked native building when the removal revision
applies. OpenBW cancels its active queue; a trainee does not become an actor
after the building is destroyed.

## Verified runs

- `tests/test_barracks_production_live.sh` passed in
  `run-data/barracks-production-live-1792194939/verification.json`: client
  construction, one native queue, 500→450 minerals, 10/16→12/16 half-supply,
  completion, dual binding of `openbw:3001`, and accepted movement. A repeated
  request produced no second command or train call.
- `BARRACKS_CANCEL_AFTER_TRAIN=1 tests/test_barracks_production_live.sh`
  passed in `run-data/barracks-production-live-1792195061/verification.json`:
  the native Barracks was retired at frame 890 during training; no Marine
  completed after the former queue deadline.
- `tests/test_barracks_bridge_restart_live.sh` passed in
  `run-data/barracks-bridge-restart-1792195397/verification.json`: both native
  participants retained park ID generation #1, native ID `openbw:8`, and
  1000 HP across a Go bridge restart without another creation.
- A two-client graphical capture passed in
  `run-data/artifacts/20261017T000416Z-5def080501a9/`. The player clicked
  the toolbar icon, placed the Barracks with the native preview, inspected it,
  clicked Train Marine, then selected and moved the completed Marine. The
  capture contains `combined.mp4`, step screenshots, and client logs.

## Recovery limits

A real park save retains the scenery, generation, and last reported native HP.
Loading starts a fresh OpenBW simulation and reconstructs the building at that
HP. A same-session Go bridge restart keeps the running OpenBW building and
queue. A full engine restart does not resume an in-progress training queue;
OpenBW starts a fresh simulation from the saved park. A real save/load at 700 HP
passed in `run-data/barracks-save-load-live-1792196839/verification.json`.

The native exit search is bounded to 128 pixels around the Barracks. A site
with no walkable, unoccupied exit in that range can accept a training order
but fail at completion under OpenBW's normal queue rules. The construction
preview checks the 4×3 footprint and current occupancy, not future egress.
