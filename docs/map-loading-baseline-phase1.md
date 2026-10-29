# Map loading baseline: Phase 1

Measured 2026-10-28 on the Raspberry Pi, with installed licensed RCT2 and StarCraft data. Source commit at measurement was `d7c74d2a17e9032b0bd0b08bc6eb91919cd29953` plus the Phase 1 instrumentation later committed as `dcfd52b`; the benchmark's USB temporary-directory fix followed as `8e369a6`. OpenRCT2 was v0.5.5 (`33aacde`, network version 0.5.5-2, plugin API 124); OpenBW source was `4b046d5`. Each map has two fresh generation workspaces. The first sample is a first selection in a fresh workspace, **not** a cold machine or cleared filesystem cache.

The benchmark used its own runtime and dynamically chosen local ports. Isolated preflight ran in a private network namespace. Each sample then started an actual headless OpenRCT2/OpenBW/Go session and waited for both `WORLD_READY ... navigation=native` and `WORLD_SCENARIO_STATUS` in the session log. No graphical client was started. The managed browser service and any active game were not stopped or replaced.

| Map (source SHA-256 prefix) | Sample | Preparation s | Isolated preflight s | Actual session startup s | Total s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fungus Woods.SC6 (`1552df55`) | first | 1.577 | 18.742 | 18.918 | 39.351 |
| Fungus Woods.SC6 (`1552df55`) | repeat | 0.873 | 18.737 | 18.919 | 38.644 |
| Extreme Heights.SC6 (`c2153130`) | first | 0.874 | 10.023 | 9.919 | 20.931 |
| Extreme Heights.SC6 (`c2153130`) | repeat | 0.875 | 10.031 | 9.909 | 20.929 |
| Saved frontier outpost park (`37e8d336`) | first | 1.091 | 10.627 | 10.512 | 22.345 |
| Saved frontier outpost park (`37e8d336`) | repeat | 1.079 | 10.635 | 10.511 | 22.340 |

Preparation sums source resolution, validation, staging, OpenRCT2 inspection, package staging, park staging, and native map generation. The individual stage times, outcomes, generation IDs, and full source hashes are in the ignored [summary.json](../run-data/map-loading-baseline-20261028/summary.json) and [load-timings.jsonl](../run-data/map-loading-baseline-20261028/runtime/load-timings.jsonl). The captured total also includes benchmark cleanup after readiness; the three named stage measurements exclude cleanup. Across these samples, repeated selection changed total time by at most 0.707 s. Isolated preflight and actual startup each dominate preparation time, and neither was skipped.

The supervisor's production timing records are appended to `run-data/park-supervisor/load-timings.jsonl` (or the configured runtime). Each record identifies map and generation, marks stages as `ok`, `failed`, or `unavailable`, and includes outcome, error, and total elapsed time. The clock is monotonic. The supervisor has no authoritative graphical client join signal, so `client_join` is explicitly `unavailable`; native readiness does not imply a client joined. A browser join, order execution, and two-client rendering were not verified by this headless baseline.

Reproduce with an idle test host and locally licensed assets:

```sh
python3 scripts/benchmark-park-loading.py \
  --stock 'Fungus Woods.SC6' \
  --stock 'Extreme Heights.SC6' \
  --save run-data/park-supervisor/saved/frontier-outpost-playable.park \
  --samples 2 \
  --output run-data/map-loading-baseline-20261028-recheck
```

`scripts/project.sh test` passed (Go, C++, Python: 164 tests with one skip, and JavaScript checks). `python3 -m unittest tests.test_park_session_supervisor` passed 15 tests, including timing failure and unavailable-stage handling. No browser build, browser join, client order, or graphical check was run because the Phase 1 benchmark does not launch a client.
