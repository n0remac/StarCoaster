# Mt. Zergling

This package loads the original `Mt. Zergling.park` from the ignored
`run-data/mt-zergling/source/` directory. The source is never modified; the
launcher stages a separate save under `run-data/mt-zergling/save/`.

OpenRCT2 reports a 202×202 map, an in-progress scenario with a 1,000 guests
by year 4 objective, and no starting rides. The player builds rides while
managing the park. Five Marines start on the owned mountain plateau, and
recurring attacks rotate through north, south, east, and west owned tiles.
The authored save contains many decorative trees. Small scenery remains
blocking but is excluded from native combat targets; large scenery and new
rides remain targetable. The default interval is 2,880 OpenBW frames,
approximately 120 seconds at the normal 42 ms frame delay. The manual
cooldown is 360 frames, approximately 15 seconds.

The source file is user authored and must stay out of Git. Use
`scripts/project.sh validate-scenario mt-zergling`,
`scripts/project.sh play mt-zergling --plan`, and
`scripts/project.sh play mt-zergling` after placing the source.
