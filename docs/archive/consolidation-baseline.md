> Historical report. Commands and script names below describe a retired prototype; use the [current workflow](../../README.md).

# v0.2 baseline — 2026-10-12

The starting source commit was `6895c72`. The tree was clean. The first playable report (`docs/first-playable-verification.md`) records a passing graphical defeat, native wall and carousel traversal, and synchronized two-client combat. It leaves victory and a live restart/reconnect unverified, and records an unstable generic live ride attack in `tests/test_world_live.sh`.

The baseline unit regressions passed on this Pi:

| Command | Result |
| --- | --- |
| `/usr/local/go/bin/go test ./...` | Pass, all Go packages |
| `ctest --test-dir build/bridge-module --output-on-failure` | Pass, 2/2 C++ tests |
| `python3 -m unittest discover -s tests -p 'test_*.py'` | Pass, 43 tests |
| `for file in tests/test_*plugin.js tests/the former v1 snapshot test; do node "$file" || exit; done` | Pass, 5 JavaScript suites |

The production boundaries are `cmd/`, `internal/`, `openrct2-plugin/`, `openrct2-patches/`, `openbw-bwapi-module/src/`, `bridge-protocol/`, and `scenarios/`. Reusable development tools live in `scripts/` and regressions in `tests/`. The `docs/archive/` folder holds earlier project proposals. Ignored `upstream/`, `build/`, and `run-data/` are dependency checkouts and local output.
