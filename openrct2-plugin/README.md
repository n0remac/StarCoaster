# OpenRCT2 remote bridge plugin

`rts-bridge.js` runs on the authoritative OpenRCT2 server and is distributed to
joined clients. It discovers park terrain and objects, sends a revisioned world
snapshot to the Go bridge, and synchronizes combat actors, target catalogs,
mission status, and Marine controls through native OpenRCT2 actions. OpenRCT2
owns park state, demolition, multiplayer state, and rendering.

`scripts/run-openrct2-host.sh` stages the plugin for the server;
`scripts/run-world-session.sh` stages it for the local client. The plugin needs
the matching native `rtsBridge` binding and staged asset pack from
`scripts/project.sh build`. Use `node tests/test_world_plugin.js` for the
headless action and discovery regression, and `scripts/project.sh test-live`
for native multiplayer checks. See the [world bridge guide](../docs/world-bridge.md).
