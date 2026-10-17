/* Test-only observer for native resource and actor state across a Go reconnect. */
registerPlugin({ name: "Next technology reconnect observer", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    let resources = null, lastReport = 0;
    context.subscribe("action.execute", function (event) {
        if (event.action === "rtsbridge.playerResources" && event.args
            && Number.isInteger(event.args.minerals) && Number.isInteger(event.args.gas))
            resources = event.args;
    });
    context.subscribe("interval.tick", function () {
        if (Date.now() - lastReport < 4000) return;
        const snapshot = rtsBridge.getActors();
        if (!snapshot || !/^[0-9a-f]{32}$/.test(snapshot.session) || !resources) return;
        lastReport = Date.now();
        const actors = snapshot.units.filter(function (unit) {
            return (unit.kind === "terran_medic" || unit.kind === "terran_vulture") && unit.hp > 0;
        }).map(function (unit) { return unit.id + ":" + unit.kind; }).sort();
        console.log("NEXT_RECONNECT_STATE session=" + snapshot.session
            + " minerals=" + resources.minerals + " gas=" + resources.gas
            + " supply=" + resources.supply_used + "/" + resources.supply_total
            + " actors=" + actors.join(","));
    });
}});
