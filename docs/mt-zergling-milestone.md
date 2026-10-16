# Mt. Zergling playable park defense

Mt. Zergling uses the user-authored `Mt. Zergling.park` as an ignored source
under `run-data/mt-zergling/source/`. The package resolver copies it to a
session save and asks OpenRCT2 for the map dimensions before building the
native map. The original file and the staged save have the same SHA-256 digest.
No park or licensed game asset is tracked by Git.

OpenRCT2 reports a 202×202 park, an in-progress objective of 1,000 guests by
year 4, 64 path tiles, three entrance elements, and no starting rides. The
player can develop the park with the normal OpenRCT2 controls. Five Marines
start on the owned plateau. Eight Zerglings arrive from rotating north,
south, east, and west owned perimeter zones on each automatic wave. The
Marine window requests extra waves through the synchronized server action.

The authored save contains many decorative trees. Mapping them all as native
obstacles exceeds OpenBW's region limit, so Mt. Zergling excludes small
scenery from native collision and combat. Large scenery still blocks native
movement. The two large trees within owned land and newly built structures
are valid park-defense targets. This scenario does not model fence jumping or
guest combat.

Wave deadlines use complete OpenBW frames. At the standard 42 ms frame
pacing, the 2,880-frame default is approximately two minutes. In the two-client
software-rendered capture, spawn-ready times were 130 seconds apart. OpenRCT2
pause and speed controls do not synchronize the OpenBW clock. An empty Marine
roster or an empty Zergling roster does not end this mode; the OpenRCT2
scenario objective remains authoritative.

## Verification

The six-minute graphical capture under ignored
`run-data/artifacts/20261016T031826Z-464fd6dfa6bf/` contains
`combined.mp4`, screenshots, client and server logs, the spawn journal,
`verification.json`, and `mt-zergling-live-evidence.json`.

The recorded session generated six attacks: three automatic and three manual.
The automatic trigger frames were 3327, 6207, and 9087, exactly 2,880 frames
apart despite the manual requests. All 48 wave units obtained unique native
actor IDs. The client snapshots showed up to 31 simultaneous Zerglings, 40
Zerglings moving more than four tiles, and both Marine and Zergling attack
orders. A wall was placed while Zerglings were alive and confirmed as
revision 2 by both native participants. Both graphical clients matched on
all 2,866 shared snapshot sequences. No RTS outcome occurred.

The separate bridge-restart run under
`run-data/artifacts/20261016T030759Z-a9bbad3e9b32/` preserved the same
session and spawn journal. Its outstanding manual wave was reconciled; one
overdue automatic attack began after recovery without a catch-up burst.

Run the offline checks with `scripts/project.sh test`. To reproduce the
graphical evidence, use
`scripts/project.sh record --scenario mt-zergling --duration 360 --mt-zergling-playthrough`,
then run `python3 scripts/verify-mt-zergling-evidence.py PATH_TO_CAPTURE`.
The `--mt-zergling-playthrough` option is a capture probe: it uses ordinary
OpenRCT2 actions for Marine reinforcement and wall construction, and clicks
the player-facing Spawn Wave button. Plain
`scripts/project.sh record --scenario mt-zergling --duration 360` also starts
and records the packaged scenario.
