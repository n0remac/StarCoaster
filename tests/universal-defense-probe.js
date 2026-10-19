/* Test-only OpenRCT2 action probe for an unmodified existing park. */
registerPlugin({ name: "Universal Defense Probe", version: "1.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        var ticks = 0, anchorSent = false, enabledSent = false, waveSent = false;
        var wavePending = false;
        var defensePending = false;
        var buildPending = false, buildingID = "", trainPending = false, trainSent = false;
        var factoryID = "", vulturePending = false, vultureSent = false;
        var lastTrainReason = "";
        var buildMode = typeof UNIVERSAL_DEFENSE_VERIFY_BUILD !== "undefined"
            && UNIVERSAL_DEFENSE_VERIFY_BUILD;
        var factoryMode = typeof UNIVERSAL_DEFENSE_VERIFY_FACTORY !== "undefined"
            && UNIVERSAL_DEFENSE_VERIFY_FACTORY;
        var barracks = buildMode && objectManager.getAllObjects("large_scenery").find(function (item) {
            return item.identifier === "starcoaster.scenery_large.terran_barracks";
        });
        var factory = factoryMode && objectManager.getAllObjects("large_scenery").find(function (item) {
            return item.identifier === "starcoaster.scenery_large.terran_factory";
        });
        function placeBuilding(object, label, onPlaced, minX, minY) {
            if (buildPending || !object) return;
            var sites = [];
            for (var y = minY || 8; y + 3 < map.size.y - 4; y++) {
                for (var x = minX || 8; x + 4 < map.size.x - 4; x++) {
                    var height = null, clear = true;
                    for (var dy = 0; dy < 3 && clear; dy++) for (var dx = 0; dx < 4; dx++) {
                        var tile = map.getTile(x + dx, y + dy), surface = null;
                        for (var index = 0; index < tile.numElements; index++) {
                            var element = tile.getElement(index);
                            if (element.isGhost) continue;
                            if (element.type === "surface") surface = element;
                            else clear = false;
                        }
                        if (!surface || surface.slope || surface.waterHeight) clear = false;
                        if (surface) {
                            var z = Number.isInteger(surface.baseZ) ? surface.baseZ : surface.baseHeight * 8;
                            if (height !== null && height !== z) clear = false;
                            height = z;
                        }
                    }
                    if (clear) sites.push({ x: x * 32, y: y * 32, z: height, direction: 0,
                        object: object.index, primaryColour: 0, secondaryColour: 0, tertiaryColour: 0 });
                }
            }
            buildPending = true;
            function next(index) {
                if (index >= sites.length) { buildPending = false; console.log(label + " no_site"); return; }
                var args = sites[index];
                context.queryAction("largesceneryplace", args, function (query) {
                    if (query.error) { next(index + 1); return; }
                    context.executeAction("largesceneryplace", args, function (result) {
                        if (result.error) { next(index + 1); return; }
                        var id = "openrct2:large_scenery:" + object.index + ":" + args.x
                            + ":" + args.y + ":" + args.z + ":0#1";
                        onPlaced(id);
                        console.log(label + " id=" + id + " cost=" + query.cost);
                        buildPending = false;
                    });
                });
            }
            next(0);
        }
        function placeBarracks() {
            placeBuilding(barracks, "UNIVERSAL_DEFENSE_BUILD", function (id) { buildingID = id; });
        }
        function placeFactory() {
            placeBuilding(factory, "UNIVERSAL_DEFENSE_FACTORY", function (id) { factoryID = id; }, 20);
        }
        function trainMarine(session) {
            if (trainPending || trainSent || !buildingID) return;
            var args = { session: session, request: 40001, unit_ids: [], verb: "train",
                unit_type: "terran_marine", target_entity_id: buildingID };
            trainPending = true;
            context.executeAction("rtsbridge.marineCommand", args, function (result) {
                trainPending = false;
                trainSent = !result.error;
                if (trainSent || result.errorMessage !== lastTrainReason) {
                    lastTrainReason = result.errorMessage;
                    console.log("UNIVERSAL_DEFENSE_TRAIN local_accepted=" + trainSent
                        + " reason=" + (result.errorMessage || "ok"));
                }
            });
        }
        function trainVulture(session) {
            if (vulturePending || vultureSent || !factoryID) return;
            var args = { session: session, request: 40002, unit_ids: [], verb: "train",
                unit_type: "terran_vulture", target_entity_id: factoryID };
            vulturePending = true;
            context.executeAction("rtsbridge.marineCommand", args, function (result) {
                vulturePending = false;
                vultureSent = !result.error;
                if (vultureSent || result.errorMessage !== lastTrainReason) {
                    lastTrainReason = result.errorMessage;
                    console.log("UNIVERSAL_DEFENSE_VULTURE local_accepted=" + vultureSent
                        + " reason=" + (result.errorMessage || "ok"));
                }
            });
        }
        context.subscribe("interval.tick", function () {
            if (network.mode !== "client" || ++ticks % 24 !== 0 || !rtsBridge) return;
            var state = rtsBridge.getActors();
            if (!state || !state.session) return;
            if (typeof UNIVERSAL_DEFENSE_VERIFY_NO_WAVE !== "undefined"
                && UNIVERSAL_DEFENSE_VERIFY_NO_WAVE) {
                if (!buildingID) placeBuilding(barracks, "UNIVERSAL_DEFENSE_BUILD",
                    function (id) { buildingID = id; }, 20, 20);
                else if (!trainSent) trainMarine(state.session);
                return;
            }
            if (defensePending) return;
            if (!anchorSent) {
                defensePending = true;
                context.executeAction("rtsbridge.configureDefense", { session: state.session,
                    anchor: typeof UNIVERSAL_DEFENSE_ANCHOR !== "undefined"
                        ? UNIVERSAL_DEFENSE_ANCHOR : [44, 56] }, function (result) {
                    console.log("UNIVERSAL_DEFENSE_ANCHOR local_accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                    if (!result.error) anchorSent = true;
                    defensePending = false;
                });
            } else if (!enabledSent) {
                defensePending = true;
                context.executeAction("rtsbridge.configureDefense", { session: state.session,
                    enabled: true }, function (result) {
                    console.log("UNIVERSAL_DEFENSE_ENABLE local_accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                    if (!result.error) enabledSent = true;
                    defensePending = false;
                });
            } else if (buildMode && !buildingID) {
                placeBarracks();
            } else if (buildMode && !trainSent) {
                trainMarine(state.session);
            } else if (buildMode && !state.units.some(function (unit) {
                return unit.kind === "terran_marine" && unit.hp > 0;
            })) {
                return;
            } else if (factoryMode && !factoryID) {
                placeFactory();
            } else if (factoryMode && !vultureSent) {
                trainVulture(state.session);
            } else if (factoryMode && !state.units.some(function (unit) {
                return unit.kind === "terran_vulture" && unit.hp > 0;
            })) {
                return;
            } else if (typeof UNIVERSAL_DEFENSE_VERIFY_MANUAL !== "undefined"
                && UNIVERSAL_DEFENSE_VERIFY_MANUAL && !waveSent && !wavePending) {
                wavePending = true;
                context.executeAction("rtsbridge.requestWave", { session: state.session,
                    request: 1, request_id: state.session + ":wave:" + network.currentPlayer.id + ":1" },
                    function (result) {
                        wavePending = false;
                        console.log("UNIVERSAL_DEFENSE_MANUAL local_accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                        if (!result.error) waveSent = true;
                    });
            }
        });
    }
});
