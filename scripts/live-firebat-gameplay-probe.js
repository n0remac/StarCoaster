/* Test-only two-client Academy dependency and mixed-squad command probe. */
registerPlugin({ name: "Firebat gameplay probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let barracks = "", barracksPlacedAt = 0, placingBarracks = false;
        let prereqRequestedAt = 0, prereqQueryPending = false, academyPlacedAt = 0;
        let trainRequested = false, duplicateRequested = false, secondRequested = false;
        let movedAt = 0, redirected = false, mixedIDs = [];
        let academyRemovedAt = 0, afterRemovalRequested = false;
        let academySite = null, placingAcademy = false;
        context.subscribe("interval.tick", function () {
            const snapshot = rtsBridge.getActors();
            if (!snapshot || !/^[0-9a-f]{32}$/.test(snapshot.session)) return;
            if (!barracksPlacedAt && !placingBarracks) {
                placingBarracks = true;
                const object = objectManager.getAllObjects("large_scenery").find(function (item) {
                    return item.identifier === "starcoaster.scenery_large.terran_barracks";
                });
                if (!object) { console.log("FIREBAT_PROBE_BARRACKS object_missing"); return; }
                const sites = [];
                for (let y = 105; y < 140; y++) for (let x = 108; x < 145; x++) {
                    if (x === 100 && y === 104) continue;
                    const origin = map.getTile(x, y).getElement(0);
                    const height = Number.isInteger(origin.baseZ) ? origin.baseZ : origin.baseHeight * 8;
                    let clear = true;
                    for (let dy = -2; dy < 5 && clear; dy++) for (let dx = -2; dx < 6; dx++) {
                        const tile = map.getTile(x + dx, y + dy);
                        if (tile.numElements !== 1 || tile.getElement(0).type !== "surface"
                            || (Number.isInteger(tile.getElement(0).baseZ)
                                ? tile.getElement(0).baseZ : tile.getElement(0).baseHeight * 8) !== height)
                            clear = false;
                    }
                    if (clear && !snapshot.units.some(function (unit) {
                        return unit.hp > 0 && unit.x > (x - 2) * 32 && unit.x < (x + 6) * 32
                            && unit.y > (y - 2) * 32 && unit.y < (y + 5) * 32;
                    })) sites.push({ x: x, y: y, z: height });
                }
                sites.sort(function (a, b) {
                    const da = Math.abs(a.x - 113) + Math.abs(a.y - 121);
                    const db = Math.abs(b.x - 113) + Math.abs(b.y - 121);
                    return da - db || a.y - b.y || a.x - b.x;
                });
                function tryBarracks() {
                    const site = sites.shift();
                    if (!site) { console.log("FIREBAT_PROBE_BARRACKS no_clear_site"); return; }
                    const args = { x: site.x * 32, y: site.y * 32, z: site.z,
                        direction: 0, object: object.index, primaryColour: 0,
                        secondaryColour: 0, tertiaryColour: 0 };
                    context.queryAction("largesceneryplace", args, function (query) {
                        if (query.error) { tryBarracks(); return; }
                        context.executeAction("largesceneryplace", args, function (result) {
                            if (!result.error) {
                                barracksPlacedAt = Date.now();
                                barracks = "openrct2:large_scenery:" + object.index + ":"
                                    + args.x + ":" + args.y + ":" + args.z + ":0#1";
                            }
                            console.log("FIREBAT_PROBE_BARRACKS accepted=" + !result.error
                                + " x=" + args.x + " y=" + args.y
                                + " reason=" + (result.errorMessage || "ok"));
                        });
                    });
                }
                tryBarracks();
            }
            if (barracksPlacedAt && !prereqRequestedAt && !prereqQueryPending
                && Date.now() - barracksPlacedAt > 8000) {
                prereqQueryPending = true;
                const args = { session: snapshot.session,
                    request: 301, unit_ids: [], verb: "train", unit_type: "terran_firebat",
                    target_entity_id: barracks };
                context.queryAction("rtsbridge.marineCommand", args, function (query) {
                    prereqQueryPending = false;
                    if (query.error) return;
                    prereqRequestedAt = Date.now();
                    context.executeAction("rtsbridge.marineCommand", args, function (result) {
                        console.log("FIREBAT_PROBE_BEFORE accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                    });
                });
            }
            if (prereqRequestedAt && !academyPlacedAt && !placingAcademy
                && Date.now() - prereqRequestedAt > 4000) {
                placingAcademy = true;
                const object = objectManager.getAllObjects("large_scenery").find(function (item) {
                    return item.identifier === "starcoaster.scenery_large.terran_academy";
                });
                if (!object) { console.log("FIREBAT_PROBE_ACADEMY object_missing"); return; }
                const sites = [];
                for (let y = 104; y < 125; y++) for (let x = 116; x < 135; x++)
                    sites.push({ x: x, y: y });
                function trySite() {
                    const site = sites.shift();
                    if (!site) { console.log("FIREBAT_PROBE_ACADEMY no_clear_site"); return; }
                    const tile = map.getTile(site.x, site.y);
                    let surface = null;
                    for (let i = 0; i < tile.numElements; i++)
                        if (tile.getElement(i).type === "surface") surface = tile.getElement(i);
                    if (!surface) { trySite(); return; }
                    const args = { x: site.x * 32, y: site.y * 32,
                        z: Number.isInteger(surface.baseZ) ? surface.baseZ : surface.baseHeight * 8,
                        direction: 0, object: object.index, primaryColour: 0,
                        secondaryColour: 0, tertiaryColour: 0 };
                    context.queryAction("largesceneryplace", args, function (query) {
                        if (query.error) { trySite(); return; }
                        context.executeAction("largesceneryplace", args, function (result) {
                            if (!result.error) { academySite = args; academyPlacedAt = Date.now(); }
                            console.log("FIREBAT_PROBE_ACADEMY accepted=" + !result.error
                                + " x=" + args.x + " y=" + args.y
                                + " reason=" + (result.errorMessage || "ok"));
                        });
                    });
                }
                trySite();
            }
            if (academyPlacedAt && !trainRequested && Date.now() - academyPlacedAt > 9000) {
                trainRequested = true;
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: 302, unit_ids: [], verb: "train", unit_type: "terran_firebat",
                    target_entity_id: barracks }, function (result) {
                    console.log("FIREBAT_PROBE_TRAIN accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (trainRequested && !duplicateRequested && Date.now() - academyPlacedAt > 10000) {
                duplicateRequested = true;
                console.log("FIREBAT_PROBE_DUPLICATE_ATTEMPT request=302");
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: 302, unit_ids: [], verb: "train", unit_type: "terran_firebat",
                    target_entity_id: barracks }, function (result) {
                    console.log("FIREBAT_PROBE_DUPLICATE rejected=" + !!result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            const firebats = snapshot.units.filter(function (unit) {
                return unit.kind === "terran_firebat" && unit.hp > 0;
            });
            const marines = snapshot.units.filter(function (unit) {
                return unit.kind === "terran_marine" && unit.hp > 0;
            });
            if (firebats.length === 1 && !secondRequested) {
                secondRequested = true;
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: 306, unit_ids: [], verb: "train", unit_type: "terran_firebat",
                    target_entity_id: barracks }, function (result) {
                    console.log("FIREBAT_PROBE_SECOND accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (firebats.length >= 2 && marines.length >= 3 && !movedAt) {
                movedAt = Date.now();
                mixedIDs = marines.slice(0, 3).concat(firebats.slice(0, 2)).map(function (unit) {
                    return unit.id;
                });
                console.log("FIREBAT_PROBE_ACTORS ids=" + mixedIDs.join(",")
                    + " hp=" + firebats[0].hp + "," + firebats[1].hp);
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: 303, unit_ids: mixedIDs, verb: "move",
                    x: firebats[0].x + 96, y: firebats[0].y + 32 }, function (result) {
                    console.log("FIREBAT_PROBE_MIXED_MOVE accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (movedAt && !redirected && Date.now() - movedAt > 300) {
                redirected = true;
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: 304, unit_ids: mixedIDs, verb: "move",
                    x: firebats[0].x + 32, y: firebats[0].y + 96 }, function (result) {
                    console.log("FIREBAT_PROBE_REDIRECT accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (movedAt && !academyRemovedAt && Date.now() - movedAt > 4000) {
                academyRemovedAt = Date.now();
                context.executeAction("largesceneryremove", { x: academySite.x, y: academySite.y,
                    z: academySite.z, direction: 0, tileIndex: 0 }, function (result) {
                    console.log("FIREBAT_PROBE_REMOVE accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (academyRemovedAt && !afterRemovalRequested && Date.now() - academyRemovedAt > 8000) {
                afterRemovalRequested = true;
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: 305, unit_ids: [], verb: "train", unit_type: "terran_firebat",
                    target_entity_id: barracks }, function (result) {
                    console.log("FIREBAT_PROBE_AFTER_REMOVE accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
        });
    }
});
