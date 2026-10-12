# v0.2 foundation verification

The generic world live regression now uses the deterministic playable park and a scenario-aligned OpenBW map while leaving the bridge in generic mode. Rides are selected before minor scenery when proxy capacity is limited. On this Pi, `tests/test_world_live.sh` passed: OpenBW destroyed carousel ride 0, OpenRCT2 confirmed native removal, and both clients agreed on the remaining ride list. Its logs are in `run-data/world-live-1791847222/`.

`python3 scripts/verify-frontier-lifecycle.py` passed two fresh headless Frontier sessions. Both reached authoritative victory with six surviving Marines and zero Zerglings. In each, client B reconnected to the same session and rendered six unique surviving actors. A complete scenario restart produced a different session ID. Logs and `verification.json` are in `run-data/frontier-lifecycle/`.

The earlier [first playable report](first-playable-verification.md) records the graphical defeat, Marine controls, and multiplayer demolition path. The v0.2 live check uses a one Zergling test scenario to make the victory and reconnect conditions deterministic; the full twelve Zergling graphical defeat remains a separate demonstration.
