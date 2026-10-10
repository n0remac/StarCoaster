# OpenRCT2 plugin

The server-distributed remote plugin is scheduled after the BWAPI runtime proof and stock OpenRCT2 multiplayer check. It will consume the validated `units.snapshot` stream on localhost and issue one synchronized custom game action per accepted snapshot. The pinned OpenRCT2 scripting API wraps custom action callbacks in `GameActionEventArgs`; read payloads from `event.args`.

The plugin will require the matching native renderer binding before it is enabled in multiplayer. This directory does not yet contain a runnable plugin.
