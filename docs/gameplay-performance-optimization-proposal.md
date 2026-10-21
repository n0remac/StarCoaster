# Proposed milestone: WASM client state and presentation throughput

Status: proposed from local measurements; the remote-laptop comparison still
requires authenticated access. No gameplay optimization is included in the
instrumentation work.

## Measured basis

Three 25-unit native battles with an offscreen WASM camera
(`run-data/performance/20261021T011517Z-4cc3ed/report.md`) maintained
22.6–22.9 median OpenBW FPS and published 7.6 snapshots/s with no omitted
actors. Chromium presented 19.2–23.4 frames/s and processed 7.8–9.5
synchronized snapshot actions/s. Its client action p95 was 11.4–11.7 ms,
versus 2.0–3.1 ms on the authoritative server. The renderer recorded zero
painted StarCraft actors in all three cases, yet the browser reported long
main-thread stalls and command-to-presented latency remained variable. One
case ended with 20 published snapshots still unapplied; the other two ended
with two and zero.

A fresh run after splitting native apply timers
(`run-data/performance/20261021T032406Z-3e7801/report.md`) was more severe:
OpenBW held 22.6 FPS, but offscreen Chromium presented 10.1 FPS and ended
235 snapshots behind. Browser long tasks reached an 11.3-second p95 per
sample, while client snapshot application took 5.8 ms at p95 and detailed
snapshot logging 4.0 ms at p95. This variability means a single client
action or painting optimization would be premature without a profile of the
stalled periods.

The native OpenRCT2 client on the same Pi, using Xvfb
(`run-data/performance/20261021T010859Z-3e7f5d/report.md`),
presented 36.6 frames/s and processed 7.5 actions/s with no backlog.

The valid 25-unit visible WASM case
(`run-data/performance/20261021T000204Z-14e4b5/report.md`) presented
3.3 frames/s while actor painting consumed 22.9 ms per presented frame.
A later centered-camera paint-suppressed case
(`run-data/performance/20261021T014241Z-32c6ee/report.md`) presented only
4.2 frames/s and ended 411 snapshots behind despite drawing zero actor
sprites and health bars. Its `PaintBridgeActors()` scope still spent 56.7 ms
per presented frame considering actors and tiles. In the visible normal case,
measured sprite and health-bar drawing each cost 0.2 ms per presented frame.
The two fights had different native combat trajectories, so these values do
not give a precise suppression speedup, but they show that sprite drawing is
unlikely to explain the whole stall. The client's visible-camera render path
and synchronized-action consumption need profiling together. An earlier
requested offscreen case painted actors and was invalidated by the stricter
camera check.

The 200-unit native battle
(`run-data/performance/20261021T003235Z-3b5f91/report.md`) had no
omitted actors or thermal throttling. Its 22.0 median OpenBW FPS is explained
primarily by the fixed 42 ms sleep plus work per frame. Go bridge and server
action costs were measurable, but they did not produce the large client
presentation gap seen above. The fresh browser run reached 63.4 °C at
2,400 MHz with no recorded throttling and about 2 GiB of available memory.
Swap had no free space, but the benchmark did not establish active swapping
as a cause. Remote Tailscale impact is still unmeasured:
the likely laptop peer appeared online, but the Pi could not authenticate
to it over SSH, and the observed connection was local and direct rather
than a remote-city path.

## Proposed scope

1. Capture a repeatable CPU profile and native frame timeline on the WASM
   client, aligned to snapshot sequence and presentation counters. Separate
   synchronized action scheduling, JavaScript-to-native conversion, actor
   application, invalidation, tile lookup and actor consideration, sprite
   painting, and other OpenRCT2 render work. Establish whether the action
   backlog causes frame stalls or grows as a consequence of them.
2. Run paired visible/offscreen and normal/suppressed-paint cases on the same
   browser hardware. Require the renderer's painted-actor counter to verify
   the camera condition and retain startup failures as invalid results.
3. Optimize the largest confirmed WASM client stage. Candidate changes may
   reduce repeated visible-tile traversal, redundant actor invalidation, or
   the cost of applying synchronized visual snapshots. Keep OpenBW
   authoritative for movement, combat, health, and ownership. Preserve
   ordered park revisions, command execution, and OpenRCT2 multiplayer
   semantics.
4. Repeat the 25, 50, 100, and 200-unit comparisons and command traces
   before and after each change. Include the remote laptop once its private
   connection is available.

## Acceptance for that milestone

- The client processes snapshots at least as fast as they arrive during a
  60-second fight, without a growing sequence backlog or omitted native units.
- Native presented FPS and command-to-presented latency improve in the
  affected case, with the same unit composition, camera, viewport, and
  graphics settings; report p95 and p99 frame times and three repeats.
- The improvement holds with StarCraft actors visible and does not regress
  the offscreen case, native client, OpenBW frame rate, scenario gameplay,
  command ordering, or existing regressions.
- Remote measurements separate client work from Tailscale RTT and state
  delivery without treating unsynchronized clocks as exact one-way latency.

The optimization work begins only after the comparison identifies a stable
client hotspot. Snapshot-rate changes, if considered, need a separate
responsiveness and ordering evaluation; they are not assumed to be the fix.
