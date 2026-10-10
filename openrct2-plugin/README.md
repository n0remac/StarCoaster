# OpenRCT2 remote plugin

`rts-bridge.js` is copied into the headless server's local plugin directory by `scripts/run-openrct2-host.sh`. OpenRCT2 distributes it to multiplayer clients. It requires the project's native `rtsBridge` binding and 12-sprite art pack; the apt OpenRCT2 v0.4.3 binary is incompatible.

Only the server connects to the BWAPI module on `127.0.0.1:39999`. It validates full version-1 snapshots for map ID `demo-flat`, rejects stale sequences, and executes `rtsbridge.applySnapshot` as a custom action. The action applies the render-only registry update on each participant. The source-to-park transform is currently explicit identity scale and zero origin for the flat POC; calibrating other maps is later work.

The plugin has passed `node --check` and a local framing/action mock. In the pinned OpenRCT2 runtime, it connected the live BWAPI publisher to the server and two headless clients applied 515 common snapshots over 65 seconds at identical OpenRCT2 ticks and coordinates. Stopping the publisher removed the actor through a synchronized action, and a new BWAPI session epoch respawned it on the server and a joined client. Graphical scene appearance and occlusion remain to be checked with RCT2 game art.
