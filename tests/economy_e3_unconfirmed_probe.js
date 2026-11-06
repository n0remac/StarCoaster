/* Frontier park regression: a native accepted order with no created building. */
registerPlugin({ name: "Economy E3 unconfirmed creation probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    let ticks = 0, barracks = false, academy = false;
    context.subscribe("interval.tick", function () {
        const state = rtsBridge.getActors();
        if (!state || !state.session || !state.units) return;
        const workers = state.units.filter(function (unit) { return unit.kind === "terran_scv"; })
            .sort(function (a, b) { return a.id.localeCompare(b.id); });
        if (workers.length < 2) return;
        ++ticks;
        function build(request, worker, type, x, y) {
            context.executeAction("rtsbridge.marineCommand", { session: state.session,
                request: request, unit_ids: [worker.id], verb: "build",
                building_type: type, tile_x: x, tile_y: y }, function (result) {
                console.log("ECONOMY_E3_UNCONFIRMED request=" + request + " type=" + type
                    + " accepted=" + !result.error + " reason=" + (result.errorMessage || "ok"));
            });
        }
        if (!barracks && ticks >= 900) {
            barracks = true;
            build(93601, workers[0], "terran_barracks", 24, 6);
        }
        if (barracks && !academy && ticks >= 2200) {
            academy = true;
            build(93602, workers[1], "terran_academy", 29, 6);
        }
    });
}});
