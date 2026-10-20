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

## Remote laptop

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
presentation data, and interrupted sessions invalid. It never promotes
startup data into a steady-state result.

OpenBW, Go, and native OpenRCT2 on the Pi use Linux `CLOCK_MONOTONIC`.
Their snapshot sequence, simulation frame, session, revision, and command
identifiers correlate stage events. Browser events use the laptop's own
monotonic clock. The report compares local processing durations, command
input to visible frame within the browser, and Tailscale round-trip times.
It does not subtract the Pi and laptop clocks or claim an exact one-way
network delay. Video capture is disabled during measurements.

Normal gameplay leaves telemetry disabled. `STARCOASTER_PERF_DIR` enables
OpenBW and Go event files, `STARCOASTER_PERF=1` enables OpenRCT2 and gateway
diagnostics, and the browser harness uses `WASM_PERF_RUN=1`. The test-only
painting switch is `STARCOASTER_SUPPRESS_PAINT=1` in native OpenRCT2 and the
matching browser URL diagnostic parameter. All benchmark data and licensed
inputs stay outside version control.
