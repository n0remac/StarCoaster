// Test-only multiplayer driver for a real 256x256 park and native map.
registerPlugin({ name: "World 256 Scale Probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    let phase = 0, request = 0, begun = 0, sent = 0, ticks = 0;
    function order(session, id, x, y) {
        const args = { session: session, request: ++request, unit_ids: [id],
            verb: "move", x: x, y: y };
        context.executeAction("rtsbridge.marineCommand", args, function (result) {
            console.log("WORLD256_ORDER request=" + request + " unit=" + id
                + " accepted=" + !result.error + " reason=" + (result.errorMessage || "ok"));
        });
        sent = Date.now();
    }
    context.subscribe("interval.tick", function () {
        const state = rtsBridge.getActors();
        if (!/^[0-9a-f]{32}$/.test(state.session)) return;
        const marines = state.units.filter(function (unit) {
            return unit.id === "openbw:1000" || unit.id === "openbw:1001";
        });
        if (marines.length !== 2) return;
        if (!begun) begun = Date.now();
        const near = marines.find(function (unit) { return unit.id === "openbw:1000"; });
        const far = marines.find(function (unit) { return unit.id === "openbw:1001"; });
        if (++ticks % 5 === 0) console.log("WORLD256_POSITION phase=" + phase + " elapsed="
            + (Date.now() - begun) + " near=" + near.x + "," + near.y
            + " far=" + far.x + "," + far.y);
        if (phase === 0 && Date.now() - begun > 1500) {
            phase = 1;
            order(state.session, near.id, 7 * 32 + 16, 5 * 32 + 16);
            order(state.session, far.id, 252 * 32 + 16, 250 * 32 + 16);
        } else if (phase === 1 && near.x >= 7 * 32 && far.x >= 252 * 32) {
            phase = 2;
            order(state.session, far.id, 128 * 32 + 16, 128 * 32 + 16);
        } else if (phase === 2 && far.x < 245 * 32 && far.y < 245 * 32) {
            phase = 3;
            console.log("WORLD256_SEQUENCE_COMPLETE elapsed=" + (Date.now() - begun));
        } else if (phase > 0 && phase < 3 && Date.now() - sent > 60000) {
            console.log("WORLD256_SEQUENCE_COMPLETE failed=phase_" + phase + "_timeout");
            phase = 4;
        }
    });
}});
