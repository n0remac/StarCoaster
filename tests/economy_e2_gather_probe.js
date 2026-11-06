/* Test-only player actions; native balances and deposits are asserted from logs. */
registerPlugin({ name: "Economy E2 gather probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    const observeOnly = typeof STARCOASTER_ECONOMY_E2_OBSERVE_ONLY !== "undefined"
        && STARCOASTER_ECONOMY_E2_OBSERVE_ONLY;
    let ticks = 0, sent = false, returned = false, refinery = false, gas = false, scouted = false;
    let trained = false, egress = false;
    context.subscribe("interval.tick", function () {
        const state = rtsBridge.getActors();
        if (!state || !state.session || !state.units) return;
        const workers = state.units.filter(function (unit) {
            return unit.alive !== false && unit.kind === "terran_scv";
        }).sort(function (a, b) { return a.id.localeCompare(b.id); });
        if (workers.length < 3) return;
        ++ticks;
        if (typeof ui !== "undefined" && ui.mainViewport && ticks % 100 === 1) {
            ui.mainViewport.rotation = 0; ui.mainViewport.zoom = 0;
            ui.mainViewport.moveTo({ x: 28 * 32, y: 10 * 32, z: 112 });
        }
        function order(request, worker, verb, extra) {
            context.executeAction("rtsbridge.marineCommand", Object.assign({ session: state.session,
                request: request, unit_ids: worker ? [worker.id] : [], verb: verb }, extra || {}),
            function (result) {
                console.log("ECONOMY_E2_ORDER request=" + request + " verb=" + verb
                    + " accepted=" + !result.error + " reason=" + (result.errorMessage || "ok"));
            });
        }
        if (!observeOnly && !scouted && ticks >= 50) {
            scouted = true;
            order(93500, workers[2], "move", { x: 33 * 32, y: 9 * 32 });
        }
        if (!observeOnly && !sent && ticks >= 900) {
            sent = true;
            order(93501, workers[0], "gather", { resource_site_id: "mineral-a", resource_generation: 1 });
            order(93502, workers[1], "gather", { resource_site_id: "mineral-b", resource_generation: 1 });
        }
        if (!observeOnly && sent && !returned && workers[0].motion === "carry") {
            returned = true;
            order(93503, workers[0], "return_cargo");
        }
        if (!observeOnly && !refinery && ticks >= 1400) {
            refinery = true;
            order(93504, workers[2], "build", { building_type: "terran_refinery",
                geyser_site_id: "geyser", tile_x: 34, tile_y: 8 });
        }
        if (!observeOnly && refinery && !gas && ticks >= 2500) {
            gas = true;
            order(93505, workers[2], "gather", { resource_site_id: "geyser", resource_generation: 2 });
        }
        if (!observeOnly && gas && !trained && ticks >= 3400) {
            trained = true;
            order(93506, null, "train", { unit_type: "terran_scv", target_entity_id: "scenario:base" });
        }
        if (trained && !egress && workers.length >= 5) {
            egress = true;
            console.log("ECONOMY_E2_TRAINED workers=" + workers.length);
        }
        if (observeOnly && ticks === 100) console.log("ECONOMY_E2_RECONNECTED workers=" + workers.length);
        if (ticks % 100 === 0) console.log("ECONOMY_E2_WORKERS tick=" + ticks + " "
            + JSON.stringify(workers.map(function (worker) {
                return { id: worker.id, motion: worker.motion, cargo: worker.cargo };
            })));
    });
}});
