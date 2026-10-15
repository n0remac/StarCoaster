// Test-only ordinary synchronized shop construction and combat probe.
registerPlugin({ name: "Live Target Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        const recovery = typeof STARCOASTER_TEST_RECOVERY !== "undefined" && STARCOASTER_TEST_RECOVERY;
        let started = 0, rideId = -1, targetId = "", commandSent = false, tile = null,
            lastAttack = 0, attackAt = 0, stopIssued = false, wallBuilt = false;
        function freeTile() {
            for (let y = 30; y <= 36; y++) for (let x = 26; x <= 36; x++) {
                const candidate = map.getTile(x, y);
                if (candidate.numElements !== 1) continue;
                const surface = candidate.getElement(0);
                if (surface.type === "surface" && surface.baseHeight === 14 && !surface.slope
                    && !surface.waterHeight) return { x: x, y: y, z: surface.baseZ || 112 };
            }
            return null;
        }
        function build() {
            tile = freeTile();
            const entry = objectManager.getAllObjects("ride").filter(function (item) {
                return item.identifier === "rct2.ride.burgb";
            })[0];
            if (!tile || !entry) { console.log("LIVE_TARGET_ERROR shop_tile_or_object_unavailable"); return; }
            const rideType = entry.rideType[0];
            context.executeAction("ridecreate", { rideType: rideType, rideObject: entry.index,
                entranceObject: 0, colour1: 0, colour2: 0, inspectionInterval: 0 }, function (created) {
                console.log("LIVE_TARGET_RIDECREATE accepted=" + !created.error + " ride=" + created.ride);
                if (created.error || !Number.isInteger(created.ride)) return;
                rideId = created.ride;
                targetId = "openrct2:ride:" + rideId + "#1";
                context.executeAction("trackplace", { x: tile.x * 32, y: tile.y * 32, z: tile.z,
                    direction: 0, ride: rideId, trackType: 262, rideType: rideType,
                    brakeSpeed: 0, colour: 0, seatRotation: 0, trackPlaceFlags: 0,
                    isFromTrackDesign: false }, function (placed) {
                    console.log("LIVE_TARGET_TRACKPLACE accepted=" + !placed.error
                        + " reason=" + (placed.errorMessage || "ok")
                        + " x=" + tile.x + " y=" + tile.y + " target=" + targetId);
                });
            });
        }
        function attack(session) {
            const args = { session: session, request: 71,
                unit_ids: recovery ? ["openbw:1003"] :
                    ["openbw:1000", "openbw:1001", "openbw:1002", "openbw:1003",
                    "openbw:1004", "openbw:1005"],
                verb: "attack", target_entity_id: targetId };
            context.queryAction("rtsbridge.marineCommand", args, function (query) {
                console.log("LIVE_TARGET_ATTACK_QUERY accepted=" + !query.error
                    + " reason=" + (query.errorMessage || "ok"));
                if (query.error) return;
                context.executeAction("rtsbridge.marineCommand", args, function (result) {
                    commandSent = !result.error;
                    if (commandSent) attackAt = Date.now();
                    console.log("LIVE_TARGET_ATTACK accepted=" + commandSent
                        + " reason=" + (result.errorMessage || "ok"));
                });
            });
        }
        function stopAttack(session) {
            context.executeAction("rtsbridge.marineCommand", { session: session, request: 72,
                unit_ids: ["openbw:1003"], verb: "stop" }, function (result) {
                console.log("LIVE_TARGET_STOP accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
            });
        }
        function buildWall() {
            const entry = objectManager.getAllObjects("wall").filter(function (item) {
                return item.identifier === "rct2.scenery_wall.wbr1";
            })[0];
            if (!entry) { console.log("LIVE_TARGET_ERROR wall_object_unavailable"); return; }
            const tile = map.getTile(20, 31);
            let z = 128;
            for (let index = 0; index < tile.numElements; index++) {
                const element = tile.getElement(index);
                if (element.type === "surface") z = element.baseZ || element.baseHeight * 8;
            }
            context.executeAction("wallplace", { x: 640, y: 992, z: z, object: entry.index,
                edge: 0, primaryColour: 0, secondaryColour: 0, tertiaryColour: 0 }, function (result) {
                console.log("LIVE_TARGET_POST_RESTART_WALL accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
            });
        }
        context.subscribe("interval.tick", function () {
            const snapshot = rtsBridge.getActors();
            if (!snapshot || !/^[0-9a-f]{32}$/.test(snapshot.session)) return;
            if (!started) { started = Date.now(); build(); }
            const elapsed = Date.now() - started;
            if (targetId && !commandSent && elapsed > 14000 && elapsed < 30000
                && Date.now() - lastAttack > 2000) {
                lastAttack = Date.now();
                attack(snapshot.session);
            }
            if (recovery && commandSent && !stopIssued && Date.now() - attackAt > 3000) {
                stopIssued = true;
                stopAttack(snapshot.session);
            }
            if (recovery && !wallBuilt && elapsed > 40000) {
                wallBuilt = true;
                buildWall();
            }
            if (elapsed > (recovery ? 72000 : 65000)) {
                console.log("LIVE_TARGET_COMPLETE ride=" + rideId + " target=" + targetId
                    + " command=" + commandSent + " actors=" + snapshot.units.map(function (actor) {
                        return actor.id;
                    }).sort().join(","));
                started = Number.MAX_SAFE_INTEGER;
            }
        });
    }
});
