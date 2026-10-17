/* Test-only graphical audit of the shared Academy and Barracks windows. */
registerPlugin({ name: "Firebat capture audit", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        const reported = {};
        let frame = 0, reportedFirebat = false, rallyIssued = false;
        let mixedReported = false;
        let deathReported = false, firebatBirth = null, mixedIDs = [];
        let followFirebat = true;
        let normalVisibility = null, normalZoom = null;
        const driver = typeof STARCOASTER_FIREBAT_CAPTURE_DRIVER !== "undefined"
            && STARCOASTER_FIREBAT_CAPTURE_DRIVER;
        if (driver) {
            ui.registerShortcut({ id: "starcoaster.firebat-capture-attack-move",
                text: "Capture mixed squad attack move", bindings: ["CTRL+SHIFT+F"],
                callback: function () {
                    const snapshot = rtsBridge.getActors();
                    if (!snapshot || mixedIDs.length < 4) return;
                    console.log("FIREBAT_CAPTURE_ATTACK_MOVE_SHORTCUT");
                    context.executeAction("rtsbridge.marineCommand", {
                        session: snapshot.session, request: 4902, unit_ids: mixedIDs,
                        verb: "attack_move", x: 3350, y: 3520
                    }, function (result) {
                        console.log("FIREBAT_CAPTURE_ATTACK_MOVE accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                        if (result.error || !ui.mainViewport) return;
                        try {
                            normalVisibility = ui.mainViewport.visibilityFlags;
                            normalZoom = ui.mainViewport.zoom;
                            // Client A records a close view of park combat;
                            // client B retains the normal scenery ordering.
                            ui.mainViewport.visibilityFlags = normalVisibility
                                | (1 << 21) | (1 << 26);
                            ui.mainViewport.zoom = -1;
                        } catch (error) {
                            console.log("FIREBAT_CAPTURE_CAMERA_ERROR " + error);
                        }
                    });
                } });
            ui.registerShortcut({ id: "starcoaster.firebat-capture-demolish",
                text: "Capture Academy demolition", bindings: ["CTRL+SHIFT+D"],
                callback: function () {
                    context.executeAction("largesceneryremove", {
                        x: 3360, y: 3328, z: 1216, direction: 0, tileIndex: 0
                    }, function (result) {
                        console.log("FIREBAT_CAPTURE_DEMOLISH accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                        if (!result.error && firebatBirth && ui.mainViewport) {
                            followFirebat = false;
                            try {
                                if (normalVisibility !== null)
                                    ui.mainViewport.visibilityFlags = normalVisibility;
                                if (normalZoom !== null) ui.mainViewport.zoom = normalZoom;
                            } catch (error) {
                                console.log("FIREBAT_CAPTURE_CAMERA_RESTORE_ERROR " + error);
                            }
                            ui.mainViewport.moveTo({ x: firebatBirth.x, y: firebatBirth.y,
                                z: 1216 });
                        }
                    });
                } });
            ui.registerShortcut({ id: "starcoaster.firebat-capture-marine-retreat",
                text: "Capture Firebat fighting after Marine retreat", bindings: ["CTRL+SHIFT+R"],
                callback: function () {
                    const snapshot = rtsBridge.getActors();
                    if (!snapshot || mixedIDs.length < 4) return;
                    const marines = mixedIDs.slice(0, 3).filter(function (id) {
                        return snapshot.units.some(function (unit) {
                            return unit.id === id && unit.hp > 0;
                        });
                    });
                    if (!marines.length) return;
                    context.executeAction("rtsbridge.marineCommand", {
                        session: snapshot.session, request: 4903, unit_ids: marines,
                        verb: "move", x: 3800, y: 4100
                    }, function (result) {
                        console.log("FIREBAT_CAPTURE_MARINE_RETREAT accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                    });
                } });
        }
        context.subscribe("interval.tick", function () {
            if (++frame % 10 !== 0) return;
            for (const classification of ["starcoaster-construction",
                    "starcoaster-barracks-info", "starcoaster-building-info"]) {
                const window = ui.getWindow(classification);
                if (!window) {
                    delete reported[classification];
                    continue;
                }
                const position = [window.x, window.y, window.width, window.height].join(",");
                if (reported[classification] !== position) {
                    reported[classification] = position;
                    console.log("FIREBAT_CAPTURE_WINDOW type=" + classification
                        + " x=" + window.x + " y=" + window.y
                        + " width=" + window.width + " height=" + window.height);
                }
            }
            const snapshot = rtsBridge.getActors();
            const actor = snapshot && snapshot.units.find(function (unit) {
                return unit.kind === "terran_firebat" && unit.hp > 0;
            });
            if (actor) {
                if (!reportedFirebat) {
                    reportedFirebat = true;
                    firebatBirth = { x: actor.x, y: actor.y };
                    if (ui.mainViewport) {
                        const tile = map.getTile(Math.floor(actor.x / 32), Math.floor(actor.y / 32));
                        let z = 0;
                        for (let index = 0; index < tile.numElements; index++) {
                            const item = tile.getElement(index);
                            if (item.type === "surface")
                                z = item.baseZ === undefined ? item.baseHeight * 8 : item.baseZ;
                        }
                        ui.mainViewport.moveTo({ x: actor.x, y: actor.y, z: z });
                    }
                    console.log("FIREBAT_CAPTURE_ACTOR id=" + actor.id
                        + " x=" + actor.x + " y=" + actor.y + " hp=" + actor.hp);
                }
                if (driver && !rallyIssued) {
                    const marines = snapshot.units.filter(function (unit) {
                        return unit.kind === "terran_marine" && unit.hp > 0;
                    }).slice(0, 3);
                    if (marines.length === 3) {
                        rallyIssued = true;
                        mixedIDs = marines.map(function (unit) { return unit.id; }).concat(actor.id);
                        context.executeAction("rtsbridge.marineCommand", {
                            session: snapshot.session, request: 4901,
                            unit_ids: mixedIDs.slice(0, 3), verb: "move",
                            x: actor.x + 96, y: actor.y + 64
                        }, function (result) {
                            console.log("FIREBAT_CAPTURE_RALLY accepted=" + !result.error
                                + " reason=" + (result.errorMessage || "ok"));
                        });
                    }
                }
                if (driver && rallyIssued && !mixedReported) {
                    const units = mixedIDs.map(function (id) {
                        return snapshot.units.find(function (unit) { return unit.id === id; });
                    });
                    if (units.every(function (unit) {
                        return unit && unit.hp > 0 && Math.abs(unit.x - actor.x) < 180
                            && Math.abs(unit.y - actor.y) < 180;
                    })) {
                        const points = mixedIDs.map(function (id) {
                            return rtsBridge.actorScreenPosition(id);
                        });
                        if (points.every(function (point) {
                            return point && point.x > 265 && point.x < 1200
                                && point.y > 100 && point.y < 700;
                        })) {
                            mixedReported = true;
                            const left = Math.min.apply(null, points.map(function (p) { return p.x; })) - 24;
                            const top = Math.min.apply(null, points.map(function (p) { return p.y; })) - 32;
                            const right = Math.max.apply(null, points.map(function (p) { return p.x; })) + 24;
                            const bottom = Math.max.apply(null, points.map(function (p) { return p.y; })) + 16;
                            console.log("FIREBAT_CAPTURE_MIXED_READY ids=" + mixedIDs.join(",")
                                + " box=" + left + "," + top + "," + right + "," + bottom);
                        }
                    }
                }
                if (followFirebat && firebatBirth && (Math.abs(actor.x - firebatBirth.x)
                        + Math.abs(actor.y - firebatBirth.y) > 160) && ui.mainViewport) {
                    const tile = map.getTile(Math.floor(actor.x / 32), Math.floor(actor.y / 32));
                    let z = 0;
                    for (let index = 0; index < tile.numElements; index++) {
                        const item = tile.getElement(index);
                        if (item.type === "surface")
                            z = item.baseZ === undefined ? item.baseHeight * 8 : item.baseZ;
                    }
                    ui.mainViewport.moveTo({ x: actor.x, y: actor.y, z: z });
                }
            } else if (reportedFirebat && !deathReported && snapshot
                    && snapshot.units.some(function (unit) { return unit.kind === "zerg_zergling"; })) {
                deathReported = true;
                console.log("FIREBAT_CAPTURE_DEATH");
            }
        });
    }
});
