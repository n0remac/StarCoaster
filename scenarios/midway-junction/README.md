# Midway Junction

Midway Junction is a 64 × 64 defense mission in a separately authored OpenRCT2 park. Defend the **Midway Ferris Wheel** in the central plaza. Six Marines begin in the western staging garden. Eight Zerglings begin at the eastern entrance, followed by an immediate four-Zergling east wave, a three-Zergling northern flank after 900 native frames, and a five-Zergling southern assault when the northern wave clears. The initial assault AI waits 450 frames so the player can position a defense. The wheel has 2,000 health in this scenario's mapping rules.

The east entrance has a short chokepoint. The north midway routes around shops, gardens, and a carousel. The south service route approaches around a separate wall. Actual wall edges and ride footprints shape native movement; public paths are also connected for the park's visual design. A single brick gate panel in the continuous western divider is destructible. With the gate intact, Marines crossing from western staging must use a long route; demolition opens a direct crossing for both Marines and Zerglings.

Use the existing squad window to select Marines and give move, attack, attack move, hold, and stop orders. The **Spawn Marine** tool accepts 1–5 Marines per request at a clear park tile. Reinforcements use the shared native spawn queue. Victory requires every wave cleared, all Zerglings eliminated, and the wheel intact. The wheel's destruction or elimination of all Marines causes defeat.

```sh
scripts/project.sh validate-scenario midway-junction
scripts/project.sh play midway-junction --plan
scripts/project.sh park midway-junction
scripts/project.sh play midway-junction
scripts/project.sh record --scenario midway-junction --duration 120
```

`park-layout.json` contains data-only ride, plaza, path, wall, and scenery placements. `package.json` uses `"generator": "layout-v1"` and references that file. The shared generator validates construction and exports actual OpenRCT2 geometry to ignored `run-data/midway-junction/save/midway-junction.park`, `fixture.json`, and `navigation-elements.json`. To author another park, copy the package structure, choose a new ID and layout, and follow `.agents/skills/starcoaster-park-design/SKILL.md`. No scenario-specific bridge or OpenBW code is required.

The supported layout format is intentionally small: 64 × 64 flat parks, stock carousel, Ferris wheel, burger and drink objects, horizontal and vertical paths, rectangular plazas, straight wall runs with explicit edge directions, and stock small or large scenery. Rides are closed visual and combat structures; operating ride entrances, guest economy, new unit types, and arbitrary terrain elevations are outside this format. The western divider remains a long detour until its gate panel is removed.
