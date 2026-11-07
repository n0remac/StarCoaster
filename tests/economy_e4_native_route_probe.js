/* Headless native E4 route probe. Uses the ordinary authenticated player action. */
registerPlugin({ name: "Economy E4 native route probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "server") return;
    let ticks = 0, accepted = false, pending = false;
    context.subscribe("interval.tick", function () {
        const state = rtsBridge.getActors();
        if (!state || !state.session || !state.units) return;
        const worker = state.units.find(function (unit) {
            return unit.kind === "terran_scv" && unit.owner === 1;
        });
        if (!worker || accepted || pending || ++ticks < 100 || ticks % 50 !== 0) return;
        pending = true;
        context.executeAction("rtsbridge.marineCommand", {
            session: state.session, request: 94701, unit_ids: [worker.id],
            verb: "gather", resource_site_id: "mineral-a", resource_generation: 1
        }, function (result) {
            pending = false;
            accepted = !result.error;
            console.log("ECONOMY_E4_NATIVE_GATHER worker=" + worker.id
                + " accepted=" + accepted + " reason=" + (result.errorMessage || "ok"));
        });
    });
}});
