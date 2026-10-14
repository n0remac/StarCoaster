// Test-only client driver for the saved Frontier ridge. Positions come from
// authoritative OpenBW actor snapshots distributed through multiplayer.
registerPlugin({ name: "Frontier Ridge Probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    const squad = [1000, 1001, 1002, 1003, 1004, 1005].map(function (id) { return "openbw:" + id; });
    let phase = 0, request = 0, began = 0, lastOrder = 0, ticks = 0;
    function order(session, ids, verb, x, y) {
        const args = { session: session, request: ++request, unit_ids: ids,
            verb: verb, x: x, y: y };
        context.executeAction("rtsbridge.marineCommand", args, function (result) {
            console.log("RIDGE_ORDER phase=" + phase + " request=" + request + " accepted="
                + !result.error + " reason=" + (result.errorMessage || "ok"));
        });
        lastOrder = Date.now();
    }
    context.subscribe("interval.tick", function () {
        const state = rtsBridge.getActors();
        if (!/^[0-9a-f]{32}$/.test(state.session)) return;
        const actors = state.units.filter(function (unit) {
            return squad.includes(unit.id) || unit.kind === "zerg_zergling";
        });
        const marine = actors.find(function (unit) { return unit.id === squad[0]; });
        if (!marine || actors.filter(function (unit) { return squad.includes(unit.id); }).length !== 6) return;
        if (!began) began = Date.now();
        if (++ticks % 3 === 0) console.log("RIDGE_POSITION phase=" + phase + " elapsed="
            + (Date.now() - began) + " units=" + actors.map(function (unit) {
                return unit.id + ":" + unit.x + "," + unit.y + "," + unit.hp + "," + unit.motion;
            }).join(";"));
        const elapsed = Date.now() - lastOrder;
        if (phase === 0 && Date.now() - began > 1500) {
            phase = 1; order(state.session, [squad[0]], "move", 12 * 32 + 16, 32 * 32 + 16);
        } else if (phase === 1 && marine.x < 13 * 32 && Math.abs(marine.y - 1040) < 80) {
            phase = 2; order(state.session, [squad[0]], "move", 20 * 32 + 16, 32 * 32 + 16);
        } else if (phase === 2 && marine.x > 19 * 32 && Math.abs(marine.y - 1040) < 80) {
            phase = 3; order(state.session, squad, "attack_move", 48 * 32 + 16, 57 * 32 + 16);
        } else if (phase === 3 && actors.some(function (unit) {
            return (squad.includes(unit.id) && unit.motion === "attack")
                || (unit.kind === "zerg_zergling" && unit.hp < 35);
        })) {
            phase = 4;
            console.log("RIDGE_POSITION phase=4 elapsed=" + (Date.now() - began) + " units="
                + actors.map(function (unit) {
                    return unit.id + ":" + unit.x + "," + unit.y + "," + unit.hp + "," + unit.motion;
                }).join(";"));
            console.log("RIDGE_SEQUENCE_COMPLETE elapsed=" + (Date.now() - began));
        } else if (phase > 0 && phase < 4 && elapsed > (phase === 3 ? 90000 : 45000)) {
            console.log("RIDGE_SEQUENCE_COMPLETE failed=phase_" + phase + "_timeout");
            phase = 5;
        }
    });
}});
