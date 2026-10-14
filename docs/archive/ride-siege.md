> Historical report. Commands and script names below describe a retired prototype; use the [current workflow](../../README.md).

# Live Frontier Carousel ride siege

This demo uses a real OpenRCT2 merry-go-round and a real OpenBW combat target. The target is a stationary Terran Missile Turret with 200 HP. It cannot attack ground units. Eight preplaced Zerglings attack it through normal BWAPI `Unit::attack` orders. No bridge code subtracts HP or kills the target. The OpenRCT2 server demolishes the ride only after an authoritative v2 snapshot reports the target destroyed.

## Reproduce on the Pi

Build the pinned native OpenRCT2 bridge and BWAPI module using the [bootstrap guide](../bootstrap.md). The game data stays in `/home/pi/games/rct2` and `/home/pi/games/starcraft` or the corresponding `RCT2_DATA_DIR` and `STARCRAFT_DATA_DIR` overrides.

> Historical command removed in v0.6; use the packaged scenario CLI.


The first command creates `run-data/ride-siege-generator/save/bridge-ride-siege.park`. The isolated demolition probe loads that saved park, executes `ridedemolish`, and verifies that nine carousel track cells disappear. It does not change the source park. The headless combat check creates `run-data/ride-siege-map/ride-siege.scm` and writes a log and verification result to `run-data/ride-siege-headless/`. The final command runs two actual OpenRCT2 graphical clients and publishes the MP4, six screenshots, filtered diagnostic logs, configuration, and result under a new `run-data/artifacts/<run-id>/` directory. Use `DEMO_OUTPUT_DIR` for a legacy output path; approved files are copied to a separate unique artifact run afterward.

## Fixture and mapping

The park fixture discovers the loaded `rct2.ride.mgr1` object, uses its ride type 33, then performs `ridecreate`, `trackplace` with `flatTrack3x3` type 266, and `ridesetname`. The saved ride has ID 100, is closed and empty, and occupies the nine cells at tiles x=18..20, y=14..16, z=112. A path and one tree are outside that footprint. The server validates the ID, name, type, object, status, empty state, and footprint before accepting siege snapshots and again before demolition.

The OpenBW map contains one Terran owned Missile Turret at pixel (736,576) and eight Zerglings near (544,488). The v2 bridge maps each Zergling into the park with `(park_x, park_y) = (bw_x - 128, bw_y - 96)`, so the target aligns with the carousel center at (608,480). OpenBW has no knowledge of the ride's collision; this is an explicit visual mapping to an accessible attack point. The `ride-siege` map is a copied terrain fixture with only the two player slots, two start locations, the turret, and eight Zerglings; the original combat map and demos are unchanged.

The pinned OpenBW game could not create buildings through BWAPI `createUnit` at runtime. The dedicated Use Map Settings fixture preplaces the turret and Zerglings. `scripts/former siege map generator` generates a standard MPQ map and verifies its scenario data by extracting it again. The installed `smpq` can read but crashes when writing on this Pi, so the script writes a minimal MPQ v1 archive with raw sectors. The source terrain remains unchanged and the source map's tutorial triggers are cleared to keep the siege running.

## Live startup and verification

The capture script loads and validates the clean park, joins both clients, waits for each to report its intact ride, then starts FFmpeg. It starts OpenBW only after recording has begun. Attack orders are scheduled for BW frame 96 and logged explicitly; screenshots are triggered by live snapshot, HP loss, and successful demolition events. This records the approach, combat, and cleared footprint without relying on a fixed wall clock delay for the attack.

The server accepts only `carousel-1` with a stable OpenBW proxy ID, monotonic sequence and BW tick, and health that never rises within a session. It translates v2 actor positions into the existing native multiplayer actor action. On the first valid destroyed state it revalidates ride 100 and executes `ridedemolish` once. Repeated destroyed snapshots and old sessions cannot initiate another action. A rejected native action is logged as failure. A new run must start from a fresh park; reconnects do not rebuild demolished rides.

The capture's `verification.json` checks all eight accepted attack orders, HP damage and one terminal target event, one successful native demolition, and each client's before and after ride state. Each client independently reports nine track cells before and zero afterward, one fewer ride overall, and the unrelated tree still present. The MP4 is not advertised in the viewer until FFmpeg finishes and `ffprobe` validates it.

## Tests and viewer

> Historical command removed in v0.6; use the packaged scenario CLI.


The Node test covers valid and malformed v2 packets, wrong target identity, HP transitions, duplicate destruction suppression, rejected demolition, changed ride identity, and session reset. The original v1 test covers patrol compatibility. The full `former prototype capture driver` command is the two client integration check and leaves the evidence in the [artifact viewer](../test-viewer.md). On this Pi the private viewer is `https://raspberrypi.tail628049.ts.net:8443/`. Tailscale Serve is tailnet only on port 8443; the existing Fabric Funnel on 443 is separate. A second device joined to the tailnet should open the run page, play and seek the combined MP4, and inspect full resolution screenshots. The Pi itself can check HTTPS with:

```sh
curl --resolve raspberrypi.tail628049.ts.net:8443:$(tailscale ip -4) \
  https://raspberrypi.tail628049.ts.net:8443/healthz
```

Current limitations: the ride disappears instantly without collapse animation; the proxy's position is a calibrated visual approximation; screenshot moments are tied to log events and can lag a frame; the initial park retains unrelated rides and guests from the source template. The carousel itself starts closed and empty.
