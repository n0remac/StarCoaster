// Test-only ordinary synchronized shop construction and combat probe.
registerPlugin({ name: "Live Target Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let started = 0, rideId = -1, targetId = "", commandSent = false, tile = null,
            lastAttack = 0;
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
                unit_ids: ["openbw:1000", "openbw:1001", "openbw:1002", "openbw:1003",
                    "openbw:1004", "openbw:1005"], verb: "attack", target_entity_id: targetId };
            context.queryAction("rtsbridge.marineCommand", args, function (query) {
                console.log("LIVE_TARGET_ATTACK_QUERY accepted=" + !query.error
                    + " reason=" + (query.errorMessage || "ok"));
                if (query.error) return;
                context.executeAction("rtsbridge.marineCommand", args, function (result) {
                    commandSent = !result.error;
                    console.log("LIVE_TARGET_ATTACK accepted=" + commandSent
                        + " reason=" + (result.errorMessage || "ok"));
                });
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
            if (elapsed > 65000) {
                console.log("LIVE_TARGET_COMPLETE ride=" + rideId + " target=" + targetId
                    + " command=" + commandSent + " actors=" + snapshot.units.map(function (actor) {
                        return actor.id;
                    }).sort().join(","));
                started = Number.MAX_SAFE_INTEGER;
            }
        });
    }
});
