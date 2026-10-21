# Laptop agent handoff: remote gameplay performance benchmark

You are working **on the laptop**. Run the graphical OpenRCT2 WASM client in
the laptop's Chromium while the Raspberry Pi remains authoritative for
OpenRCT2, both native OpenBW participants, and the Go world bridge. The Pi
benchmark runner coordinates cases; its `--clients remote` mode starts
`browser/live-test.mjs` on this laptop over SSH and copies the laptop metrics
back. The test process and Chromium rendering execute locally on the laptop.

## Objective and current evidence

Produce at least one valid, 60-second, 25-unit fighting benchmark over a
private Tailscale HTTPS connection, with a browser movement command traced
through OpenBW and back to a presented browser frame. Add a matched Pi-local
comparison and visible/offscreen and paint-suppressed cases if the first run
is stable. The existing Pi-local artifact
`run-data/performance/20261021T032406Z-3e7801/report.md` is a local-only
baseline: OpenBW held 22.6 FPS, while Pi Chromium presented
10.1 FPS and ended 235 snapshots behind. The proposed follow-up is in
[gameplay-performance-optimization-proposal.md](gameplay-performance-optimization-proposal.md).

The Pi checkout was clean at `9b7d1c2` when this handoff was written. Use
that commit or a later compatible revision on both machines. Do not copy
licensed RCT2 or StarCraft files to the laptop; the private Pi browser origin
provisions RCT2 into the ignored Chromium profile and serves the patched
WASM bundle and StarCraft visuals.

## Preconditions to establish

1. Confirm the laptop has Tailscale, `/usr/bin/chromium`, Node, an SSH server,
   and a StarCoaster checkout with `browser/package-lock.json`. Run
   `npm ci --prefix browser` in that checkout. Keep the checkout, Chromium
   profile, and result directory on storage with several free GiB. Verify
   `git rev-parse HEAD` matches the Pi build revision.
2. Arrange noninteractive **Pi → laptop SSH** for the laptop user that owns
   the checkout. Authorize the Pi's **public** SSH key for that account and
   verify from the Pi that `ssh -o BatchMode=yes <laptop-ssh-host> 'command -v
   node; test -x /usr/bin/chromium; pwd'` succeeds. Never transfer a private
   key or put authentication material in benchmark artifacts. If SSH cannot
   be authorized, stop and report that limitation; manually collected browser
   logs cannot be treated as a correlated runner case.
3. On the Pi, verify a **separate private Tailscale Serve HTTPS origin**
   points to the benchmark gateway at `127.0.0.1:8092`. That gateway forwards
   `/ws` to the isolated OpenRCT2 host on port `11754`. Preserve the normal
   private service on port `8091` and its Serve route. Never use Funnel.
   Check the route from the laptop after the benchmark case starts, including
   the browser's required isolation headers and a working `/ws` connection.
4. Record whether the laptop is physically near the Pi or on a different
   network. A direct Tailscale path can occur in either situation. A
   same-network run is a **near baseline**, not the remote-city result.

Keep private hostnames, IP addresses, origin URLs, and SSH account details in
local shell variables or ignored local notes. Substitute them for the angle
bracket placeholders below; do not commit or paste them into a shared report.

## Run sequence

Open a Pi shell from the laptop and run the commands from the Pi checkout.
The Pi runner launches the laptop's Node/Chromium process; do not open a
second browser test against the case while it is measuring.
Set `SC_LAPTOP_HOST`, `SC_LAPTOP_ROOT`, `SC_PRIVATE_ORIGIN`, and
`SC_TAILSCALE_PEER` in that Pi shell using the verified private values.

First run one remote 25-unit fighting case:

```sh
python3 scripts/benchmark-gameplay-performance.py \
  --counts 25 --workloads fighting --cameras visible \
  --painting normal --clients remote \
  --warmup 15 --measure 60 \
  --remote-host "$SC_LAPTOP_HOST" \
  --remote-root "$SC_LAPTOP_ROOT" \
  --remote-url "$SC_PRIVATE_ORIGIN" \
  --tailscale-peer "$SC_TAILSCALE_PEER"
```

The command prints `run-data/performance/<run-id>/` on the Pi. The runner
uses ports `40110–40112`, `11754`, and `8092`, keeping the normal Pi game
session separate. A cold laptop profile may spend minutes provisioning and
building OpenRCT2's object index; that time is excluded from the measurement.
The runner retries a failed browser startup once and marks an unready or
interrupted case invalid. Keep video and screenshots disabled for timing.

Once that case is valid, use the **same viewport, zoom, graphics settings,
profile, and Pi build** for the comparison cases. The harness fixes its
viewport at `1280×800`. Run visible and away camera positions with normal
and suppressed StarCraft painting. Pair laptop and Pi-local cases at the
same unit count and workload. Run a representative 50-unit visible normal
fight three times with each client. Use `--plan` before a larger `--matrix`
run to estimate duration. A full matrix may run for hours because every
case has a warm-up, at least 60 seconds of measurement, and browser startup.

For the matched comparison, change the first command's case options to
`--counts 25 --workloads fighting --cameras visible away --painting normal
suppressed --clients local remote --repeats 1`. For the three-repeat case,
use `--counts 50 --workloads fighting --cameras visible --painting normal
--clients local remote --repeats 3`. Keep the remote connection options and
the warm-up and measurement lengths in both commands.

To measure the **network effect**, repeat a matched configuration with this
same laptop on a near network and on the intended remote network. Preserve
the same browser profile and display configuration. If only one location is
available, report client and transport measurements but leave the near-vs-
remote network effect unmeasured. Pi-local Chromium is useful diagnostic
evidence, but it also consumes Pi resources and is not a controlled network
baseline for the laptop.

## Inspect and return evidence

For every case, inspect `summary.json` and `report.md` under the printed Pi
run directory. Keep the original `metadata.json`, `events.jsonl`,
`system.jsonl`, and `network.jsonl`; the runner also copies the laptop's
`browser-events.jsonl`, `browser-system.jsonl`, `browser-network.jsonl`, and
`runtime.json` into the case directory. Do not alter validity flags by hand.

A successful remote case must show:

- `valid: true`, a full 60-second measurement window, native OpenBW combat,
  zero omitted units, and a laptop Chromium client with native presented-frame
  metrics.
- Correlated snapshot sequence/frame identifiers and a movement command
  observed at browser input, server validation, Go forwarding, OpenBW
  execution, first native movement, browser receipt, and presentation. Record
  `command-to-visible` only for a visible normal-paint case.
- Laptop Chromium CPU, memory, long-task, WebSocket byte/rate, and native
  frame-time distributions; Pi process and thermal measurements; in-run
  Tailscale RTT, variation, loss samples, direct/DERP path, and interruptions.
- The report's ranked suspected bottlenecks, plus a short interpretation of
  whether a client stall, action backlog, transport delay, or Pi resource
  pressure best explains the measured case. Support multiple causes when the
  evidence does. Never subtract laptop and Pi monotonic timestamps directly
  or state an exact one-way network delay without synchronization.

Return the run ID, the Pi report path, both Git revisions, the exact command
with private values redacted, pass/fail for each case, and the remaining
limits. Keep raw logs and licensed assets in ignored `run-data/` or `build/`.
Check shared artifacts for private IP addresses, origin URLs, account names,
authentication material, licensed files, and captures before sharing. If a
case fails to join, has omitted actors, lacks native presentation, or has no
in-run Tailscale RTT, retain it as invalid and report the reason.

Do not change simulation authority, native combat, multiplayer ordering, or
the production Pi session. Fix only a concrete harness defect needed to make
the remote run valid, verify it, and commit that fix separately from the
benchmark data. Do not implement gameplay performance optimizations during
this handoff.
