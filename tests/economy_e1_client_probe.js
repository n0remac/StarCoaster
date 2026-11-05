/* Test-only native client probe: one authenticated SCV training order. */
registerPlugin({ name: "Economy E1 client probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client" || typeof ui === "undefined") return;
    const observeOnly = typeof STARCOASTER_ECONOMY_E1_OBSERVE_ONLY !== "undefined"
        && STARCOASTER_ECONOMY_E1_OBSERVE_ONLY;
    let ticks = 0, submitted = false, completed = false, attempts = 0;
    context.subscribe("interval.tick", function () {
        const state = rtsBridge.getActors();
        if (!state || !state.session || !state.units) return;
        ++ticks;
        if (ticks % 100 === 1 && ui.mainViewport) {
            ui.mainViewport.rotation = 0;
            ui.mainViewport.zoom = 0;
            ui.mainViewport.moveTo({ x: 28 * 32, y: 10 * 32, z: 112 });
        }
        const live = state.units.filter(function (unit) { return unit.alive !== false; });
        const workers = live.filter(function (unit) { return unit.kind === "terran_scv"; });
        const minerals = live.filter(function (unit) { return unit.kind === "mineral_field"; });
        const geysers = live.filter(function (unit) { return unit.kind === "vespene_geyser"; });
        if (ticks % 100 === 1) console.log("ECONOMY_E1_CLIENT frame=" + (state.bw_tick || 0)
            + " workers=" + workers.length + " minerals=" + minerals.length
            + " geysers=" + geysers.length + " session=" + state.session);
        if (!observeOnly && !submitted && ticks > 50 && ticks % 80 === 1 && attempts < 60
            && workers.length === 4 && minerals.length === 6
            && geysers.length === 1) {
            const request = 91001 + attempts++;
            context.executeAction("rtsbridge.marineCommand", { session: state.session,
                request: request, unit_ids: [], verb: "train", unit_type: "terran_scv",
                target_entity_id: "scenario:base" }, function (result) {
                if (!result.error) submitted = true;
                console.log("ECONOMY_E1_TRAIN_ORDER accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
            });
        }
        if (submitted && !completed && workers.length >= 5) {
            completed = true;
            const ids = workers.map(function (unit) { return unit.id; }).sort();
            console.log("ECONOMY_E1_TRAIN_COMPLETE workers=" + workers.length
                + " ids=" + JSON.stringify(ids));
        }
    });
}});
