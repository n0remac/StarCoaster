// Test-only native actor occupancy construction probe.
registerPlugin({ name: "Live Overlap Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let started = 0, phase = 0, phaseStarted = 0, request = 0;
        const marine = "openbw:1003", wallX = 640, wallY = 992;
        function object() {
            return objectManager.getAllObjects("wall").filter(function (item) {
                return item.identifier === "rct2.scenery_wall.wbr1";
            })[0];
        }
        function groundZ() {
            const tile = map.getTile(20, 31);
            for (let index = 0; index < tile.numElements; index++) {
                const element = tile.getElement(index);
                if (element.type === "surface") return element.baseZ || element.baseHeight * 8;
            }
            return 128;
        }
        function order(session) {
            const args = { session: session, request: ++request, unit_ids: [marine],
                verb: "move", x: wallX, y: 1008 };
            context.executeAction("rtsbridge.marineCommand", args, function (result) {
                console.log("LIVE_OVERLAP_MOVE accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
            });
        }
        function build(position) {
            const entry = object();
            if (!entry) { console.log("LIVE_OVERLAP_ERROR wall_object_missing"); return; }
            context.executeAction("wallplace", { x: wallX, y: wallY, z: groundZ(),
                object: entry.index, edge: 0, primaryColour: 0,
                secondaryColour: 0, tertiaryColour: 0 }, function (result) {
                console.log("LIVE_OVERLAP_BUILD accepted=" + !result.error
                    + " marine_x=" + position.x + " marine_y=" + position.y
                    + " reason=" + (result.errorMessage || "ok"));
            });
        }
        function remove() {
            context.executeAction("wallremove", { x: wallX, y: wallY, z: groundZ(),
                direction: 0 }, function (result) {
                console.log("LIVE_OVERLAP_REMOVE accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
            });
        }
        context.subscribe("interval.tick", function () {
            const snapshot = rtsBridge.getActors();
            const unit = snapshot.units.filter(function (actor) { return actor.id === marine; })[0];
            if (!unit || !/^[0-9a-f]{32}$/.test(snapshot.session)) return;
            if (!started) { started = Date.now(); phaseStarted = started; order(snapshot.session); }
            if (phase === 0 && Math.abs(unit.x - wallX) <= 4 && Math.abs(unit.y - 1008) <= 8) {
                phase = 1; phaseStarted = Date.now(); build(unit);
            } else if (phase === 0 && Date.now() - started > 25000) {
                phase = 9; console.log("LIVE_OVERLAP_ERROR marine_did_not_reach_wall");
            } else if (phase === 1 && Date.now() - phaseStarted > 10000) {
                phase = 2; phaseStarted = Date.now(); remove();
            } else if (phase === 2 && Date.now() - phaseStarted > 12000) {
                phase = 3;
                console.log("LIVE_OVERLAP_COMPLETE x=" + unit.x + " y=" + unit.y
                    + " actors=" + snapshot.units.map(function (actor) {
                        return actor.id;
                    }).sort().join(","));
            }
            if (phase > 0 && phase < 3 && Date.now() % 1000 < 50)
                console.log("LIVE_OVERLAP_POSITION phase=" + phase + " x=" + unit.x
                    + " y=" + unit.y);
        });
    }
});
