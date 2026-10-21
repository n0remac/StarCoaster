# Gameplay performance benchmarks

`scripts/benchmark-gameplay-performance.py` runs a deterministic native OpenBW
population in the existing example-defense park. It uses the normal world
bridge, synchronized OpenRCT2 actions, multiplayer transport, and private WASM
client. The runner creates its scenario and native map under ignored
`run-data/performance/<run-id>/`; no generated units are simulated by the
benchmark itself. Diagnostics are opt-in and do not add a gameplay action.

## Local run

Build the native engines and browser client, then run:

```sh
scripts/project.sh build
OPENRCT2_WASM_LOCAL=1 scripts/project.sh build-wasm
python3 scripts/benchmark-gameplay-performance.py \
  --counts 50 --workloads fighting --warmup 15 --measure 60
```

The default test uses alternate local ports 40110–40112, 11754, and 8092,
so an ordinary session on 40010–40012, 11753, and 8091 can remain active.
The first browser launch may take several minutes to provision RCT2 data and
build OpenRCT2 indexes; measurement starts only after it joins and sees a
native actor snapshot. The browser profile stays in ignored `build/` for reuse.
The benchmark needs installed licensed RCT2 and StarCraft inputs, a built
native session, Chromium, Node dependencies, and a built WASM bundle.
Fighting cases hold the existing native Zerg assault until the measured
window begins, then release it through a test-only file gate; a run without
observed native attack state is invalid.

Use `--plan` to inspect a case list. `--matrix` covers 0, 10, 25, 50, 100,
and 200 units, the applicable idle/moving/fighting workloads, visible/away
camera positions, and normal/suppressed StarCraft painting. It repeats the
representative 50-unit fight three times. Each measured case lasts at least
60 seconds, with a separate warm-up. The `--clients native` option exercises
an OpenRCT2 native client where available. `--painting suppressed` is a
test-only client setting; snapshots and synchronized actions still run.

On a Pi without a graphical desktop, a native-client smoke run can use Xvfb:

```sh
mkdir -p run-data/performance/tmp
TMPDIR="$PWD/run-data/performance/tmp" xvfb-run -a \
  -s '-screen 0 1280x800x24' \
  python3 scripts/benchmark-gameplay-performance.py \
  --counts 25 --workloads fighting --clients native --measure 60
```

The Xvfb display path is different from Chromium and should be labeled in
comparisons.

Add `--overhead-pair` to run a matching minimal timing baseline before each
fully instrumented case. The baseline retains only OpenBW frame timing so
the report can compare p95 simulation work against the 5% overhead target.
OpenBW publishes detailed build, serialization, and write timing for one in
four combat snapshots. The Go bridge records every received snapshot for
unit counts, payload sizes, rates, attack state, and omitted-unit checks.
This keeps the gameplay publication cadence unchanged.

In the measured three-pair 25-unit native comparison
(`run-data/performance/20261021T004959Z-5b631c/report.md`), additional
OpenBW p95 frame work was 3.47%, 3.64%, and 6.30%. The median met the 5%
target, while one repeat exceeded it. Treat small frame-cost differences
near this spread as uncertain and rerun overhead pairs on the target host.

To regenerate a report after an analysis-code change without replaying the
game, run:

```sh
python3 scripts/benchmark-gameplay-performance.py \
  --reanalyze-run run-data/performance/RUN_ID_HERE
```

The report records both the measured build's Git revision and the analysis
revision.

## Remote laptop

The [laptop agent handoff](gameplay-performance-laptop-agent.md) gives a
step-by-step remote run, validity checks, and evidence requirements.

The laptop needs an SSH-reachable checkout, Chromium, the browser test's Node
dependencies, and access to the **private** Pi HTTPS origin that points to
the isolated benchmark gateway. Do not use Tailscale Funnel. Run a case with
`--clients remote --remote-host <ssh-host> --remote-root <checkout>` plus
`--remote-url <private-https-origin> --tailscale-peer <peer>`. The runner starts
the browser test over SSH, copies its JSONL data back, and pings the peer
throughout measurement. Its artifacts replace peer names and URLs with
`<private-peer>`; the command line is intentionally absent from metadata.

Use the same viewport (1280×800), zoom (0), and graphics settings for
comparisons. A local Pi Chromium run measures the full client pipeline but
also consumes Pi CPU and memory; it is not a substitute for the remote laptop
comparison.

## Evidence and clock model

Each run writes `metadata.json`, `events.jsonl`, `system.jsonl`,
`network.jsonl`, `summary.json`, and `report.md` under
`run-data/performance/<run-id>/`. Per-case raw logs remain there for audit.
The report marks omitted native actors, failed browser joins, missing native
presentation data, and interrupted sessions invalid. Visible normal cases
must actually paint bridge actors; offscreen and paint-suppressed cases must
paint none. It never promotes startup data into a steady-state result.

OpenBW, Go, and native OpenRCT2 on the Pi use Linux `CLOCK_MONOTONIC`.
Their snapshot sequence, simulation frame, session, revision, and command
identifiers correlate stage events. Browser events use the laptop's own
monotonic clock. The report compares local processing durations, command
input to visible frame within the browser, and Tailscale round-trip times.
It does not subtract the Pi and laptop clocks or claim an exact one-way
network delay. Command traces may span the warm-up and measurement windows;
the report pairs browser input, server validation, Go forwarding, OpenBW
execution, first native movement, client action processing, and the first
presented frame containing that movement snapshot. The report distinguishes
that presented state from a visible actor when the camera is away or painting
is suppressed. Client FPS counts native presented frames over the entire
steady-state window, including intervals with no frame. Video capture is
disabled during measurements.

In the renderer table, paint time includes `PaintBridgeActors()` tile lookup
and actor consideration. The opt-in suppression mode skips sprite and health
bar drawing after the actor-position check; the report lists those drawing
costs separately. A low FPS result with suppression enabled therefore does
not, by itself, identify sprite drawing as the cause.

The native apply breakdown times allocation, sorting, previous-state indexing,
state comparison, visual updates, tile indexing, invalidation, and detailed
snapshot logging independently. Older artifacts collected before the split
show those added columns as unavailable when reanalyzed.

Normal gameplay leaves telemetry disabled. `STARCOASTER_PERF_DIR` enables
OpenBW and Go event files, `STARCOASTER_PERF=1` enables OpenRCT2 and gateway
diagnostics, and the browser harness uses `WASM_PERF_RUN=1`. The test-only
painting switch is `STARCOASTER_SUPPRESS_PAINT=1` in native OpenRCT2 and the
matching browser URL diagnostic parameter. All benchmark data and licensed
inputs stay outside version control.
