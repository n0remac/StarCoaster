---
name: starcoaster-demo
description: Launch and record the Frontier Outpost scenario, capture screenshots or MP4, and inspect two-client synchronization evidence.
---

# Demo Frontier Outpost

Use `scripts/project.sh park` after layout changes and `scripts/project.sh run` for an interactive session. For an artifact viewer run, use `scripts/project.sh record --duration 85 --video-layout combined`; `--video-layout single` is a lighter capture, and `--cycle-rotations` saves all camera views. The recorder accepts FPS, output width, CRF, encoder preset, display size, graphics mode, and frame pacing options; inspect `--help` for current names.

For multiplayer evidence, use both graphical clients and inspect `verification.json` for shared snapshot sequences, mismatches, demolition, and outcome. The artifact viewer reads screenshots, filtered logs, video metadata, and verified MP4s from `run-data/artifacts/`. Keep screenshots and video under that ignored directory; follow `docs/licensing.md` for game assets. State whether the run is a full gameplay demonstration or a capture-only check.
