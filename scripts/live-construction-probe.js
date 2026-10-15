// Test-only synchronized OpenRCT2 construction and native actor movement probe.
registerPlugin({ name: "Live Construction Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let phase = 0, started = 0, phaseStarted = 0, tick = 0, request = 0;
        let bothClientsAt = 0;
        const waitForSecondClient = typeof STARCOASTER_VISUAL_TWO_CLIENTS !== "undefined"
            && STARCOASTER_VISUAL_TWO_CLIENTS;
        const x = 20 * 32, y = 31 * 32, marine = "openbw:1003";
        function wallObject() {
            const match = objectManager.getAllObjects("wall").filter(function (entry) {
                return entry.identifier === "rct2.scenery_wall.wbr1";
            })[0];
            return match && match.index;
        }
        function wallPresent() {
            const tile = map.getTile(20, 31);
            for (let index = 0; index < tile.numElements; index++)
                if (tile.getElement(index).type === "wall") return true;
            return false;
        }
        function groundZ() {
            const tile = map.getTile(20, 31);
            for (let index = 0; index < tile.numElements; index++) {
                const element = tile.getElement(index);
                if (element.type === "surface")
                    return element.baseZ === undefined ? element.baseHeight * 8 : element.baseZ;
            }
            return 112;
        }
        function order(session, destinationX) {
            const args = { session: session, request: ++request, unit_ids: [marine],
                verb: "move", x: destinationX, y: 1008 };
            context.queryAction("rtsbridge.marineCommand", args, function (query) {
                console.log("LIVE_CONSTRUCTION_ORDER_QUERY phase=" + phase + " accepted=" + !query.error
                    + " reason=" + (query.errorMessage || "ok"));
                if (query.error) return;
                context.executeAction("rtsbridge.marineCommand", args, function (result) {
                    console.log("LIVE_CONSTRUCTION_ORDER phase=" + phase + " accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            });
        }
        function build() {
            try {
                const object = wallObject(), z = groundZ();
                console.log("LIVE_CONSTRUCTION_ATTEMPT object=" + object + " z=" + z);
                if (!Number.isInteger(object) || wallPresent()) {
                    console.log("LIVE_CONSTRUCTION_ERROR wall_object_or_tile_unavailable"); return;
                }
                const args = { x: x, y: y, z: z, object: object, edge: 0,
                    primaryColour: 0, secondaryColour: 0, tertiaryColour: 0 };
                context.queryAction("wallplace", args, function (query) {
                    console.log("LIVE_CONSTRUCTION_QUERY accepted=" + !query.error
                        + " reason=" + (query.errorMessage || "ok"));
                    if (query.error) return;
                    context.executeAction("wallplace", args, function (result) {
                        console.log("LIVE_CONSTRUCTION_BUILD accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                    });
                });
            } catch (error) { console.log("LIVE_CONSTRUCTION_ERROR " + error); }
        }
        function remove() {
            context.executeAction("wallremove", { x: x, y: y, z: groundZ(), direction: 0 }, function (result) {
                console.log("LIVE_CONSTRUCTION_REMOVE accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
            });
        }
        context.subscribe("interval.tick", function () {
            const snapshot = rtsBridge.getActors();
            const unit = snapshot.units.filter(function (actor) { return actor.id === marine; })[0];
            if (!unit || !/^[0-9a-f]{32}$/.test(snapshot.session)) return;
            if (!started) {
                started = Date.now();
                console.log("LIVE_CONSTRUCTION_ACTORS initial=" + snapshot.units.map(function (actor) {
                    return actor.id;
                }).sort().join(","));
            }
            const now = Date.now();
            if (waitForSecondClient && !bothClientsAt && (network.players || []).length >= 3)
                bothClientsAt = now;
            if (++tick % 4 === 0) console.log("LIVE_CONSTRUCTION_POSITION phase=" + phase
                + " x=" + unit.x + " y=" + unit.y + " hp=" + unit.hp
                + " wall=" + wallPresent());
            if (phase === 0 && now - started > 5000
                && (!waitForSecondClient || (bothClientsAt && now - bothClientsAt > 3000))) {
                phase = 1; phaseStarted = now; build();
            } else if (phase === 1 && now - phaseStarted > 9000) {
                phase = 2; phaseStarted = now; order(snapshot.session, 736);
            } else if (phase === 2 && (unit.x > 700 || now - phaseStarted > 22000)) {
                phase = 3; phaseStarted = now; remove();
            } else if (phase === 3 && now - phaseStarted > 9000) {
                phase = 4; phaseStarted = now; order(snapshot.session, 496);
            } else if (phase === 4 && (unit.x < 550 || now - phaseStarted > 22000)) {
                phase = 5;
                console.log("LIVE_CONSTRUCTION_ACTORS final=" + snapshot.units.map(function (actor) {
                    return actor.id;
                }).sort().join(","));
                console.log("LIVE_CONSTRUCTION_COMPLETE x=" + unit.x + " y=" + unit.y);
            }
        });
    }
});
