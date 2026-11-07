/* Test-only browser probe for an automatically generated finite economy. */
registerPlugin({ name: "Economy E4 ordinary park probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    let ticks = 0, allTicks = 0, trainAccepted = false, gatherAccepted = false;
    let trained = false, gathering = false, trainPending = false, gatherPending = false;
    context.subscribe("interval.tick", function () {
        allTicks++;
        if (network.mode !== "client" || typeof ui === "undefined") return;
        const state = rtsBridge.getActors();
        if (allTicks % 100 === 1) console.log("ECONOMY_E4_TICK mode=" + network.mode
            + " bridge=" + (typeof rtsBridge) + " session=" + (state && state.session)
            + " units=" + (state && state.units && state.units.length));
        if (!state || !state.session || !state.units) return;
        const live = state.units.filter(function (unit) { return unit.alive !== false; });
        const workers = live.filter(function (unit) { return unit.kind === "terran_scv"; })
            .sort(function (a, b) { return a.id.localeCompare(b.id); });
        const minerals = live.filter(function (unit) { return unit.kind === "mineral_field"; });
        const geysers = live.filter(function (unit) { return unit.kind === "vespene_geyser"; });
        if (!workers.length) return;
        ticks++;
        if (ticks % 100 === 1) {
            if (ui.mainViewport) {
                ui.mainViewport.rotation = 0; ui.mainViewport.zoom = 0;
                ui.mainViewport.moveTo({ x: workers[0].x, y: workers[0].y,
                    z: workers[0].z || 112 });
            }
            console.log("ECONOMY_E4_CLIENT workers=" + workers.length + " minerals="
                + minerals.length + " geysers=" + geysers.length + " session=" + state.session);
        }
        if (workers.length < 4 || minerals.length < 6 || geysers.length < 1) return;
        function order(request, args, done) {
            context.executeAction("rtsbridge.marineCommand", Object.assign({ session: state.session,
                request: request }, args), function (result) {
                console.log("ECONOMY_E4_ORDER request=" + request + " accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
                done(!result.error);
            });
        }
        if (!trainAccepted && !trainPending && ticks >= 50 && ticks % 50 === 0) {
            trainPending = true;
            order(94601, { unit_ids: [], verb: "train", unit_type: "terran_scv",
                target_entity_id: "scenario:base" }, function (accepted) {
                trainPending = false; trainAccepted = accepted;
            });
        }
        if (!gatherAccepted && !gatherPending && ticks >= 100 && ticks % 50 === 0) {
            gatherPending = true;
            order(94602, { unit_ids: [workers[0].id], verb: "gather",
                resource_site_id: "mineral-a", resource_generation: 1 }, function (accepted) {
                gatherPending = false; gatherAccepted = accepted;
            });
        }
        if (trainAccepted && workers.length >= 5 && !trained) {
            trained = true;
            console.log("ECONOMY_E4_TRAINED workers=" + workers.length
                + " ids=" + JSON.stringify(workers.map(function (worker) { return worker.id; })));
        }
        if (gatherAccepted && !gathering && workers[0].motion === "gather") {
            gathering = true;
            console.log("ECONOMY_E4_GATHERING worker=" + workers[0].id
                + " target=" + workers[0].resource_target);
        }
    });
}});
