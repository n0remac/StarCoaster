---
name: starcoaster-verify
description: Select and run StarCoaster unit, integration, and graphical regressions after bridge, navigation, combat, synchronization, or rendering changes.
---

# Verify StarCoaster changes

Read the root `AGENTS.md` for authority boundaries and commands. Use `scripts/project.sh test` for the standard Go, C++, Python, and JavaScript gate. Select live checks for the changed behavior: `tests/test_frontier_native_navigation_live.sh` for park geometry and demolition routes, `tests/test_world_live.sh` for generic two-client target removal, `tests/test_playable_start_live.sh` for the normal launcher and starting wave, and `scripts/verify-frontier-lifecycle.py` for victory, reconnect, and restart. `scripts/project.sh test-live` runs these plus ridge, 256×256, spawn, and scenario runtime checks.

Live checks need built engines and locally licensed RCT2 and StarCraft data. Report each command's result and the `run-data/` evidence path. Keep failures visible; see `docs/first-playable-verification.md` and `docs/foundation-verification.md` for prior findings.
