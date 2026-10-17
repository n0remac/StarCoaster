# Mt. Zergling

This package loads the original `Mt. Zergling.park` from the ignored
`run-data/mt-zergling/source/` directory. The source is never modified; the
launcher stages a separate save under `run-data/mt-zergling/save/`.

OpenRCT2 reports a 202×202 map, an in-progress scenario with a 1,000 guests
by year 4 objective, and no starting rides. The player builds rides while
managing the park. Five Marines start on the owned mountain plateau, and
recurring attacks start near the north, south, east, and west map edges.
Each edge has a broad group of candidate tiles. An attack tries its rotating
edge first and uses another edge if occupied. Temporarily blocked attacks
remain queued and resume when a safe tile and native actor capacity are
available.
The authored save contains many decorative trees. Small scenery is excluded
from native combat and collision. The two large trees inside the authored
owned plateau, plus new rides, remain combat targets. Large trees outside the
owned plateau still block movement but cannot draw attacks out of the park.
The default interval is 2,880 OpenBW frames,
approximately 120 seconds at the normal 42 ms frame delay. The manual
cooldown is 360 frames, approximately 15 seconds.
The recorded two-client graphical run took about 130 seconds between
automatic wave spawns because rendering and capture added frame overhead.

The OpenRCT2 park objective stays in charge of normal park success and
failure. Zerglings and Marines can be eliminated without ending this mode.
The original save has no starting rides or guests; use the usual OpenRCT2
construction and park controls to develop it. OpenRCT2 pause and speed
controls do not synchronize the OpenBW simulation clock, so wave timing is
measured on complete native frames rather than the in-game date.
The first joined player is the park operator and receives OpenRCT2 construction
and park management permissions. If that player leaves, the next connected
player becomes the operator.

The source file is user authored and must stay out of Git. Use
`scripts/project.sh validate-scenario mt-zergling`,
`scripts/project.sh play mt-zergling --plan`, and
`scripts/project.sh play mt-zergling` after placing the source.
For a two-client graphical verification with a real six-minute video, run
`scripts/project.sh record --scenario mt-zergling --duration 360 --mt-zergling-playthrough`.
For a focused headless check of park opening, ride construction, and all four
native edge routes, run `python3 tests/test_mt_zergling_gameplay_live.py`.
That test shortens the wave timer in an isolated ignored runtime copy; the
packaged scenario keeps the normal 2,880-frame interval.
The test-only capture option uses ordinary OpenRCT2 actions to place one wall
while Zerglings are alive and clicks Spawn Wave in the Marine window. It saves
the video, screenshots, logs, and verification data under ignored
`run-data/artifacts/`.

## StarCraft construction and production

The StarCraft button in the upper-right construction toolbar opens the
Barracks and Academy placement menu. Place each building on clear park ground;
normal OpenRCT2 clearance and ownership rules apply. Click a completed Barracks
to inspect its native HP, queue, and Marine and Firebat buttons. Firebat training
requires a completed, Terran-owned native Academy. Click the Academy to inspect
its native identity, synchronization status, and HP (up to 600). It has no
production queue. Demolishing the last Academy disables new Firebat orders.

Terran player 1 starts with 500 minerals, 250 gas, and a native Supply Depot
outside the mapped park. OpenBW spends resources and checks supply, queue
capacity, and technology when a training order executes. These resources are
a fixed scenario fixture; there is no mining or gas harvesting in this mode.
The Supply Depot does not appear as a park construction option. Completed
Marines and Firebats use the same selection and squad orders, including mixed
groups. A bridge reconnect preserves native resources, queues, buildings, and
actors while the engines remain running. A full engine restart reconstructs
buildings and their saved HP from the park, but does not restore a training
queue that was still active.
