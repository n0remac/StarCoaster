---
name: starcoaster-demo
description: Play or capture a packaged StarCoaster scenario and inspect graphical and two-client synchronization evidence.
---

# Play and capture a scenario

Use `scripts/project.sh play ID` for an existing build, or `scripts/project.sh start --scenario ID` for bootstrap. Regenerate changed layout data with `scripts/project.sh park ID`. `scripts/project.sh record --scenario ID --duration 85 --video-layout combined` captures two clients, screenshots, logs, and video. Use `--video-layout single` for a lighter video; `--cycle-rotations` is a Frontier-only four-view capture. Check `scripts/project.sh record --help` for current capture options.

Inspect the run's `verification.json` for scenario identity, shared snapshot sequences, mismatches, and outcome. Frontier captures also have specialized visual checks. The artifact viewer reads ignored captures in `run-data/artifacts/`; see `docs/test-viewer.md`. Keep screenshots, MP4s, and local game assets out of commits under `docs/licensing.md`. Report whether the run demonstrated gameplay or only capture and synchronization.
