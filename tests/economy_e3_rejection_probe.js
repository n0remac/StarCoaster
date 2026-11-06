/* Native graphical player-command rejection on the 50-mineral E1 fixture. */
registerPlugin({ name: "Economy E3 rejection probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    let ticks = 0, sent = false;
    context.subscribe("interval.tick", function () {
        const state = rtsBridge.getActors();
        if (!state || !state.session || !state.units) return;
        const worker = state.units.find(function (unit) { return unit.kind === "terran_scv"; });
        if (!worker || sent || ++ticks < 900) return;
        sent = true;
        for (const [request, type, x, y] of [[93701, "terran_supply_depot", 34, 10],
            [93702, "terran_academy", 29, 6]]) {
            context.executeAction("rtsbridge.marineCommand", { session: state.session,
                request: request, unit_ids: [worker.id], verb: "build",
                building_type: type, tile_x: x, tile_y: y }, function (result) {
                console.log("ECONOMY_E3_REJECT request=" + request + " type=" + type
                    + " accepted=" + !result.error + " reason=" + (result.errorMessage || "ok"));
            });
        }
    });
}});
