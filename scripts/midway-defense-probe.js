/* Test-only normal multiplayer actions for a defended Midway run. */
registerPlugin({ name: "Midway Defense Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        var completed = 0, lastSpawn = 0, lastMove = 0, lastHold = 0, lastAttack = 0;
        var moved = false, held = false, attacked = false, repositioned = false, request = 9000, ticks = 0;
        var sites = [[1360, 976], [1200, 1008], [1296, 848], [1296, 1232]];
        function command(session, verb, ids, target, callback) {
            var args = {session: session, request: ++request, unit_ids: ids, verb: verb};
            if (target) args.target_entity_id = target;
            else {args.x = 848; args.y = 896;}
            context.executeAction("rtsbridge.marineCommand", args, callback);
        }
        context.subscribe("interval.tick", function () {
            if (++ticks < 80 || ticks % 20 !== 0 || !rtsBridge) return;
            var snapshot = rtsBridge.getActors();
            if (!snapshot || !snapshot.session || !Array.isArray(snapshot.units)) return;
            var marines = snapshot.units.filter(function (u) { return u.kind === "terran_marine" && u.hp > 0; });
            if (ticks % 80 === 0) console.log("MIDWAY_ROSTER marines=" + marines.length
                + " players=" + (network.players || []).length + " self=" + network.currentPlayer.id);
            if (marines.length < 6) return;
            var now = Date.now();
            if (completed < sites.length && marines.length >= 6 + 5 * (completed + 1)) completed++;
            if (completed < sites.length && now - lastSpawn > 3000) {
                var site = sites[completed];
                lastSpawn = now;
                console.log("MIDWAY_SUBMIT spawn=" + (completed + 1) + " tick=" + ticks);
                context.executeAction("rtsbridge.spawnMarine", {session: snapshot.session,
                    request_id: snapshot.session + ":midway:" + (completed + 1), count: 5,
                    x: site[0], y: site[1]}, function (result) {
                    console.log("MIDWAY_SPAWN accepted=" + !result.error + " reason=" + (result.errorMessage || "ok"));
                });
            }
            var initial = marines.filter(function (u) { return /^openbw:100[0-5]$/.test(u.id); }).map(function (u) { return u.id; });
            var runtime = marines.filter(function (u) { return /^openbw:3[0-9]+$/.test(u.id); }).map(function (u) { return u.id; });
            if (!moved && now - lastMove > 3000) {
                lastMove = now;
                command(snapshot.session, "move", initial, null, function (result) {
                    moved = !result.error;
                    console.log("MIDWAY_MOVE accepted=" + moved + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (!held && runtime.length >= 5 && now - lastHold > 3000) {
                lastHold = now;
                command(snapshot.session, "hold", runtime.slice(0, 5), null, function (result) {
                    held = !result.error;
                    console.log("MIDWAY_HOLD accepted=" + held + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (!repositioned && runtime.length >= 10) {
                context.executeAction("rtsbridge.marineCommand", {session: snapshot.session,
                    request: ++request, unit_ids: runtime.slice(5, 10), verb: "move", x: 1136, y: 1056}, function (result) {
                    repositioned = !result.error;
                    console.log("MIDWAY_REINFORCEMENT_MOVE accepted=" + repositioned
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (!attacked && runtime.length >= 5 && now - lastAttack > 3000) {
                lastAttack = now;
                command(snapshot.session, "attack", initial,
                    "openrct2:wall:31:864:960:112:0#1", function (result) {
                    attacked = !result.error;
                    console.log("MIDWAY_ATTACK accepted=" + attacked + " reason=" + (result.errorMessage || "ok"));
                });
            }
        });
    }
});
