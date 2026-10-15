// Test-only ordinary large scenery and footpath construction/removal.
registerPlugin({ name: "Live Scenery Path Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let started = 0, phase = 0, largeTile = null, pathTile = null, smallTile = null;
        let smallObject = null;
        function tiles() {
            const result = [];
            for (let y = 36; y >= 29; y--) for (let x = 37; x >= 27; x--) {
                const tile = map.getTile(x, y);
                if (tile.numElements !== 1) continue;
                const surface = tile.getElement(0);
                if (surface.type !== "surface" || surface.baseHeight !== 14
                    || surface.slope || surface.waterHeight) continue;
                result.push({ x: x, y: y, z: surface.baseZ || 112 });
            }
            return result;
        }
        function placeLarge(candidates, index, object) {
            if (index >= candidates.length) {
                console.log("LIVE_SCENERY_ERROR large_scenery_placement_unavailable"); return;
            }
            const tile = candidates[index];
            const args = { x: tile.x * 32, y: tile.y * 32, z: tile.z, direction: 0,
                object: object.index, primaryColour: 0, secondaryColour: 0, tertiaryColour: 0 };
            context.queryAction("largesceneryplace", args, function (query) {
                if (query.error) { placeLarge(candidates, index + 1, object); return; }
                context.executeAction("largesceneryplace", args, function (result) {
                    if (result.error) { placeLarge(candidates, index + 1, object); return; }
                    largeTile = tile;
                    console.log("LIVE_SCENERY_LARGE_BUILD accepted=true x=" + tile.x + " y=" + tile.y);
                    const next = candidates.filter(function (item) {
                        return Math.abs(item.x - tile.x) + Math.abs(item.y - tile.y) >= 4;
                    })[0];
                    if (!next) { console.log("LIVE_SCENERY_ERROR path_tile_unavailable"); return; }
                    pathTile = next;
                    context.executeAction("footpathplace", { x: next.x * 32, y: next.y * 32,
                        z: next.z, object: 4, railingsObject: 0, direction: 0,
                        slopeType: 0, slopeDirection: 0, constructFlags: 0 }, function (placed) {
                        console.log("LIVE_SCENERY_PATH_BUILD accepted=" + !placed.error
                            + " reason=" + (placed.errorMessage || "ok"));
                    });
                    smallTile = candidates.filter(function (item) {
                        return Math.abs(item.x - tile.x) + Math.abs(item.y - tile.y) >= 4
                            && Math.abs(item.x - next.x) + Math.abs(item.y - next.y) >= 4;
                    })[0];
                    smallObject = objectManager.getAllObjects("small_scenery")[0];
                    if (!smallTile || !smallObject) {
                        console.log("LIVE_SCENERY_ERROR small_scenery_inputs_unavailable"); return;
                    }
                    context.executeAction("smallsceneryplace", { x: smallTile.x * 32,
                        y: smallTile.y * 32, z: smallTile.z, direction: 0, quadrant: 0,
                        object: smallObject.index, primaryColour: 0, secondaryColour: 0,
                        tertiaryColour: 0 }, function (placed) {
                        console.log("LIVE_SCENERY_SMALL_BUILD accepted=" + !placed.error
                            + " reason=" + (placed.errorMessage || "ok"));
                    });
                });
            });
        }
        context.subscribe("interval.tick", function () {
            const snapshot = rtsBridge.getActors();
            if (!snapshot || !/^[0-9a-f]{32}$/.test(snapshot.session)) return;
            if (!started) started = Date.now();
            const elapsed = Date.now() - started;
            if (phase === 0 && elapsed > 3000) {
                phase = 1;
                const object = objectManager.getAllObjects("large_scenery").filter(function (entry) {
                    return entry.identifier === "rct2.scenery_large.sip";
                })[0];
                if (!object) { console.log("LIVE_SCENERY_ERROR large_scenery_object_unavailable"); return; }
                placeLarge(tiles(), 0, object);
            } else if (phase === 1 && elapsed > 18000 && largeTile && pathTile && smallTile) {
                phase = 2;
                context.executeAction("largesceneryremove", { x: largeTile.x * 32,
                    y: largeTile.y * 32, z: largeTile.z, direction: 0, tileIndex: 0 }, function (result) {
                    console.log("LIVE_SCENERY_LARGE_REMOVE accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
                context.executeAction("footpathremove", { x: pathTile.x * 32,
                    y: pathTile.y * 32, z: pathTile.z }, function (result) {
                    console.log("LIVE_SCENERY_PATH_REMOVE accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
                context.executeAction("smallsceneryremove", { x: smallTile.x * 32,
                    y: smallTile.y * 32, z: smallTile.z, object: smallObject.index,
                    quadrant: 0 }, function (result) {
                    console.log("LIVE_SCENERY_SMALL_REMOVE accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            } else if (phase === 2 && elapsed > 35000) {
                phase = 3;
                console.log("LIVE_SCENERY_COMPLETE actors=" + snapshot.units.map(function (unit) {
                    return unit.id;
                }).sort().join(","));
            }
        });
    }
});
