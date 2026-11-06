/* Test-only player-action Depot interruption and another-SCV resume. */
registerPlugin({ name: "Economy E3 lifecycle probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client" || typeof ui === "undefined") return;
    let ticks = 0, moved = false, requested = false, stopped = false, resumed = false;
    let stoppedAt = 0;
    context.subscribe("interval.tick", function () {
        const state = rtsBridge.getActors();
        if (!state || !state.session || !state.units) return;
        ++ticks;
        const workers = state.units.filter(function (unit) {
            return unit.alive !== false && unit.kind === "terran_scv";
        }).sort(function (a, b) { return a.id.localeCompare(b.id); });
        if (workers.length < 2) return;
        if (ui.mainViewport && ticks % 100 === 1) {
            ui.mainViewport.rotation = 0; ui.mainViewport.zoom = 0;
            ui.mainViewport.moveTo({ x: 34 * 32, y: 10 * 32, z: 112 });
        }
        function order(request, worker, verb, extra) {
            const args = Object.assign({ session: state.session, request: request,
                unit_ids: worker ? [worker.id] : [], verb: verb }, extra || {});
            context.executeAction("rtsbridge.marineCommand", args, function (result) {
                console.log("ECONOMY_E3_LIFECYCLE request=" + request + " verb=" + verb
                    + " accepted=" + !result.error + " reason=" + (result.errorMessage || "ok"));
            });
        }
        if (!moved && ticks > 50) {
            moved = true;
            order(93201, workers[0], "move", { x: 38 * 32, y: 10 * 32 });
            order(93202, workers[1], "move", { x: 33 * 32, y: 10 * 32 });
        }
        if (!requested && ticks > 900) {
            requested = true;
            order(93203, workers[0], "build", {
                building_type: "terran_supply_depot", tile_x: 34, tile_y: 10 });
        }
        const depotObject = objectManager.getAllObjects("large_scenery").find(function (object) {
            return object.identifier === "starcoaster.scenery_large.terran_supply_depot";
        });
        const site = map.getTile(34, 10);
        let projected = false;
        for (let i = 0; i < site.numElements; ++i) {
            const element = site.getElement(i);
            if (depotObject && element.type === "large_scenery" && element.object === depotObject.index)
                projected = true;
        }
        if (requested && projected && !stopped) {
            stopped = true;
            stoppedAt = ticks;
            order(93204, workers[0], "stop");
        }
        if (stopped && !resumed && ticks > stoppedAt + 120) {
            resumed = true;
            order(93205, workers[1], "resume_construction",
                { target_entity_id: "build:1:93203" });
        }
    });
}});
