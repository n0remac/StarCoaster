/* Test-only full-path Marine order interruption probe. */
registerPlugin({ name: "Marine Controls Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let phase = 0, initialX = 0, reverseX = 0, redirectedAt = 0;
        function order(session, request, x, y, callback) {
            const args = { session: session, request: request, unit_ids: ["openbw:1000"],
                verb: "move", x: x, y: y };
            context.queryAction("rtsbridge.marineCommand", args, function (query) {
                if (query.error) return;
                context.executeAction("rtsbridge.marineCommand", args, function (result) {
                    console.log("MARINE_CONTROL_ORDER request=" + request + " accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                    if (!result.error) callback();
                });
            });
        }
        context.subscribe("interval.tick", function () {
            const snapshot = rtsBridge.getActors();
            const marine = snapshot.units.find(function (unit) {
                return unit.id === "openbw:1000" && unit.hp > 0;
            });
            if (!marine || !snapshot.session) return;
            if (phase === 0) {
                phase = -1;
                initialX = marine.x;
                order(snapshot.session, 1, initialX - 160, marine.y, function () {
                    phase = 1;
                    console.log("MARINE_CONTROL_START x=" + initialX + " y=" + marine.y);
                });
            } else if (phase === 1 && marine.x <= initialX - 24) {
                phase = -2;
                reverseX = marine.x;
                order(snapshot.session, 2, initialX + 96, marine.y, function () {
                    phase = 2;
                    redirectedAt = Date.now();
                    console.log("MARINE_CONTROL_REDIRECT x=" + reverseX + " y=" + marine.y);
                });
            } else if (phase === 2 && marine.x >= reverseX + 16) {
                phase = 3;
                console.log("MARINE_CONTROL_PASS x=" + marine.x
                    + " redirect_ms=" + (Date.now() - redirectedAt));
            }
        });
    }
});
