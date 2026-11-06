/* Test-only native Refinery cancel and geyser restoration through player actions. */
registerPlugin({ name: "Economy E3 Refinery cancel probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client" || typeof ui === "undefined") return;
    let ticks = 0, moved = false, requested = false, canceled = false, projectedAt = 0;
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
        function order(request, verb, units, extra) {
            context.executeAction("rtsbridge.marineCommand", Object.assign({
                session: state.session, request: request, unit_ids: units, verb: verb,
            }, extra || {}), function (result) {
                console.log("ECONOMY_E3_REFINERY_CANCEL request=" + request + " verb=" + verb
                    + " accepted=" + !result.error + " reason=" + (result.errorMessage || "ok"));
            });
        }
        if (!moved && ticks > 50) {
            moved = true;
            order(93401, "move", [worker.id], { x: 33 * 32, y: 9 * 32 });
        }
        if (!requested && ticks > 900) {
            requested = true;
            order(93402, "build", [worker.id], { building_type: "terran_refinery",
                geyser_site_id: "geyser", tile_x: 34, tile_y: 8 });
        }
        if (!requested || canceled) return;
        const object = objectManager.getAllObjects("large_scenery").find(function (item) {
            return item.identifier === "starcoaster.scenery_large.terran_refinery";
        });
        if (!object) return;
        const tile = map.getTile(34, 8);
        for (let i = 0; i < tile.numElements; ++i) {
            const element = tile.getElement(i);
            if (element.type === "large_scenery" && element.object === object.index) {
                if (!projectedAt) {
                    projectedAt = ticks;
                    console.log("ECONOMY_E3_REFINERY_PROJECTED tick=" + ticks);
                }
                break;
            }
        }
        if (projectedAt && ticks > projectedAt + 80) {
            canceled = true;
            order(93403, "cancel_construction", [],
                { target_entity_id: "build:1:93402" });
        }
    });
}});
