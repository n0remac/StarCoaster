/* Test-only player-action orders for every supported finite Terran building. */
registerPlugin({ name: "Economy E3 all buildings probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    const steps = [
        ["terran_barracks", 24, 15, 0],
        ["terran_academy", 29, 16, 1],
        ["terran_factory", 34, 15, 2],
        ["terran_armory", 39, 16, 3],
        ["terran_supply_depot", 37, 12, 2],
        ["terran_command_center", 20, 22, 0],
        ["terran_refinery", 34, 8, 1]
    ];
    let ticks = 0, sent = 0, scouted = false;
    context.subscribe("interval.tick", function () {
        const state = rtsBridge.getActors();
        if (!state || !state.session || !state.units) return;
        const workers = state.units.filter(function (unit) {
            return unit.alive !== false && unit.kind === "terran_scv";
        }).sort(function (a, b) { return a.id.localeCompare(b.id); });
        if (workers.length < 4) return;
        ++ticks;
        if (!scouted && ticks >= 50) {
            scouted = true;
            [[24, 14], [30, 15], [36, 14], [40, 15]].forEach(function (point, index) {
                context.executeAction("rtsbridge.marineCommand", { session: state.session,
                    request: 93300 + index, unit_ids: [workers[index].id], verb: "move",
                    x: point[0] * 32, y: point[1] * 32 }, function (result) {
                    console.log("ECONOMY_E3_ALL_SCOUT worker=" + index + " accepted=" + !result.error);
                });
            });
        }
        if (sent >= steps.length || ticks < 900 + sent * 800) return;
        const step = steps[sent], worker = workers[step[3]], request = 93400 + sent;
        ++sent;
        const extra = step[0] === "terran_refinery" ? { geyser_site_id: "geyser" } : {};
        context.executeAction("rtsbridge.marineCommand", Object.assign({ session: state.session,
            request: request, unit_ids: [worker.id], verb: "build",
            building_type: step[0], tile_x: step[1], tile_y: step[2] }, extra), function (result) {
            console.log("ECONOMY_E3_ALL request=" + request + " type=" + step[0]
                + " site=" + step[1] + "," + step[2] + " accepted=" + !result.error
                + " reason=" + (result.errorMessage || "ok"));
        });
        if (sent === steps.length) console.log("ECONOMY_E3_ALL_ORDERS_SENT");
    });
}});
