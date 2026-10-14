// Test-only client driver. Commands go through the same multiplayer action as
// map clicks; positions are read back from OpenBW's native actor snapshots.
registerPlugin({ name: "Frontier Native Navigation Probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    const ids = [1000, 1001, 1002, 1003, 1004, 1005].map(function (n) { return "openbw:" + n; });
    const wall = "openrct2:wall:31:896:1120:112:0#1";
    const carousel = "openrct2:ride:0#1";
    let phase = 0, request = 0, started = 0, lastOrder = 0, tick = 0;
    function actors() {
        const snapshot = rtsBridge.getActors();
        const marines = snapshot.units.filter(function (unit) { return ids.includes(unit.id); });
        return { session: snapshot.session, marines: marines };
    }
    function order(session, verb, x, y, target) {
        const args = { session: session, request: ++request, unit_ids: ids, verb: verb };
        if (target) args.target_entity_id = target;
        else { args.x = x; args.y = y; }
        context.executeAction("rtsbridge.marineCommand", args, function (result) {
            console.log("NATIVE_NAV_ORDER phase=" + phase + " request=" + request + " verb=" + verb
                + " accepted=" + !result.error + " reason=" + (result.errorMessage || "ok"));
        });
        lastOrder = Date.now();
    }
    function wallPresent() {
        const tile = map.getTile(28, 35);
        for (let i = 0; i < tile.numElements; i++) {
            const element = tile.getElement(i);
            if (element.type === "wall" && element.object === 31) return true;
        }
        return false;
    }
    function carouselPresent() { return !!map.getRide(0); }
    context.subscribe("interval.tick", function () {
        const state = actors();
        if (state.marines.length !== 6 || !/^[0-9a-f]{32}$/.test(state.session)) return;
        if (!started) started = Date.now();
        if (++tick % 8 === 0) console.log("NATIVE_NAV_POSITION phase=" + phase + " elapsed="
            + (Date.now() - started) + " units=" + state.marines.map(function (unit) {
                return unit.id + ":" + unit.x + "," + unit.y;
            }).join(";"));
        const elapsed = Date.now() - lastOrder;
        if (phase === 0 && Date.now() - started > 2000) {
            phase = 1; order(state.session, "move", 720, 460);
        } else if (phase === 1 && (state.marines.every(function (u) { return u.y < 650; }) || elapsed > 30000)) {
            phase = 2; order(state.session, "move", 1200, 1120);
        } else if (phase === 2 && (state.marines.every(function (u) { return u.x > 1000; }) || elapsed > 40000)) {
            phase = 3; order(state.session, "attack", 0, 0, wall);
        } else if (phase === 3 && !wallPresent()) {
            console.log("NATIVE_NAV_WALL_REMOVED elapsed=" + (Date.now() - started));
            phase = 31; lastOrder = Date.now();
        } else if (phase === 31 && elapsed > 4000) {
            phase = 4; order(state.session, "move", 720, 1120);
        } else if (phase === 3 && elapsed > 10000) {
            order(state.session, "attack", 0, 0, wall);
        } else if (phase === 4 && (state.marines.every(function (u) { return u.x < 780; }) || elapsed > 40000)) {
            phase = 5; order(state.session, "attack", 0, 0, carousel);
        } else if (phase === 4 && elapsed > 8000 && request === 4) {
            order(state.session, "move", 720, 1120);
        } else if (phase === 5 && !carouselPresent()) {
            console.log("NATIVE_NAV_CAROUSEL_REMOVED elapsed=" + (Date.now() - started));
            phase = 51; lastOrder = Date.now();
        } else if (phase === 51 && elapsed > 4000) {
            phase = 6; order(state.session, "move", 624, 592);
        } else if (phase === 5 && elapsed > 10000) {
            if (request >= 8) {
                phase = 8;
                console.log("NATIVE_NAV_SEQUENCE_COMPLETE failed=carousel_attack_unavailable");
            } else order(state.session, "attack", 0, 0, carousel);
        } else if (phase === 6 && state.marines.some(function (u) {
            return 576 <= u.x && u.x < 672 && 544 <= u.y && u.y < 640;
        })) {
            phase = 7;
            console.log("NATIVE_NAV_POSITION phase=7 elapsed=" + (Date.now() - started) + " units="
                + state.marines.map(function (unit) { return unit.id + ":" + unit.x + "," + unit.y; }).join(";"));
            console.log("NATIVE_NAV_SEQUENCE_COMPLETE elapsed=" + (Date.now() - started));
        } else if (phase === 6 && elapsed > 40000) {
            phase = 8;
            console.log("NATIVE_NAV_SEQUENCE_COMPLETE failed=carousel_route_timeout");
        }
    });
}});
