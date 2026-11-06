/* Test-only player-action Refinery over the observed geyser site. */
registerPlugin({ name: "Economy E3 Refinery probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client" || typeof ui === "undefined") return;
    let ticks = 0, moved = false, requested = false;
    context.subscribe("interval.tick", function () {
        const state = rtsBridge.getActors();
        if (!state || !state.session || !state.units) return;
        ++ticks;
        const worker = state.units.find(function (unit) {
            return unit.id === "openbw:2506" && unit.kind === "terran_scv";
        });
        if (!worker) return;
        if (ui.mainViewport && ticks % 100 === 1) {
            ui.mainViewport.rotation = 0; ui.mainViewport.zoom = 0;
            ui.mainViewport.moveTo({ x: 34 * 32, y: 8 * 32, z: 112 });
        }
        if (!moved && ticks > 50) {
            moved = true;
            context.executeAction("rtsbridge.marineCommand", { session: state.session,
                request: 93301, unit_ids: [worker.id], verb: "move",
                x: 33 * 32, y: 9 * 32 }, function (result) {
                console.log("ECONOMY_E3_REFINERY_MOVE accepted=" + !result.error);
            });
        }
        if (!requested && ticks > 900) {
            requested = true;
            context.executeAction("rtsbridge.marineCommand", { session: state.session,
                request: 93302, unit_ids: [worker.id], verb: "build",
                building_type: "terran_refinery", geyser_site_id: "geyser",
                tile_x: 34, tile_y: 8 }, function (result) {
                console.log("ECONOMY_E3_REFINERY_BUILD accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
            });
        }
    });
}});
