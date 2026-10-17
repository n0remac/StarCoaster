/* Test-only park construction, native production, supply, and mixed orders. */
registerPlugin({ name: "Medic and Vulture gameplay probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        const capture = typeof STARCOASTER_CAPTURE_NEXT_TECH !== "undefined"
            && STARCOASTER_CAPTURE_NEXT_TECH === true;
        const buildings = ["terran_barracks", "terran_factory", "terran_supply_depot", "terran_academy"];
        const placed = {}, locations = {}, nativeIDs = {}, sessionSeen = { value: "" };
        let next = 0, pending = false, lastPlacement = 0, beforeAcademy = false;
        let trained = false, mixed = false, mixedAt = 0, academyRemovedAt = 0;
        let afterAcademy = false, depotRemovedAt = 0, afterDepot = false, request = 700;
        let firebatRequested = false, firebatLogged = false, combatOrdered = false;
        let healRequested = false, healingObserved = false;
        function train(kind, building, retry) {
            const snapshot = rtsBridge.getActors();
            const requestId = retry || ++request;
            context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                request: requestId, unit_ids: [], verb: "train",
                unit_type: kind, target_entity_id: nativeIDs[building] }, function (result) {
                console.log("NEXT_PROBE_TRAIN type=" + kind + " accepted=" + !result.error
                    + " request=" + requestId + " reason=" + (result.errorMessage || "ok"));
            });
        }
        function place(kind, done) {
            const object = objectManager.getAllObjects("large_scenery").find(function (item) {
                return item.identifier === "starcoaster.scenery_large." + kind;
            });
            if (!object) { console.log("NEXT_PROBE_ERROR missing_object=" + kind); return; }
            const sites = [];
            for (let y = 104; y < 139; y++) for (let x = 105; x < 139; x++)
                sites.push({ x: x, y: y });
            sites.sort(function (a, b) {
                const da = Math.abs(a.x - (108 + next * 5)) + Math.abs(a.y - 113);
                const db = Math.abs(b.x - (108 + next * 5)) + Math.abs(b.y - 113);
                return da - db || a.y - b.y || a.x - b.x;
            });
            function attempt() {
                const site = sites.shift();
                if (!site) { console.log("NEXT_PROBE_ERROR no_site=" + kind); return; }
                const width = kind === "terran_barracks" || kind === "terran_factory" ? 4 : 3;
                const height = width === 4 ? 3 : 2;
                if (rtsBridge.getActors().units.some(function (unit) {
                    return unit.hp > 0 && unit.x >= (site.x - 1) * 32
                        && unit.x < (site.x + width + 1) * 32
                        && unit.y >= (site.y - 1) * 32
                        && unit.y < (site.y + height + 1) * 32;
                })) { attempt(); return; }
                const tile = map.getTile(site.x, site.y);
                let surface = null;
                for (let i = 0; i < tile.numElements; i++)
                    if (tile.getElement(i).type === "surface") surface = tile.getElement(i);
                if (!surface) { attempt(); return; }
                const args = { x: site.x * 32, y: site.y * 32,
                    z: Number.isInteger(surface.baseZ) ? surface.baseZ : surface.baseHeight * 8,
                    direction: 0, object: object.index, primaryColour: 0,
                    secondaryColour: 0, tertiaryColour: 0 };
                context.queryAction("largesceneryplace", args, function (query) {
                    if (query.error) { attempt(); return; }
                    context.executeAction("largesceneryplace", args, function (result) {
                        if (result.error) { attempt(); return; }
                        nativeIDs[kind] = "openrct2:large_scenery:" + object.index + ":"
                            + args.x + ":" + args.y + ":" + args.z + ":0#1";
                        locations[kind] = args;
                        placed[kind] = Date.now(); lastPlacement = placed[kind];
                        console.log("NEXT_PROBE_PLACE type=" + kind + " accepted=true id=" + nativeIDs[kind]);
                        done();
                    });
                });
            }
            attempt();
        }
        context.subscribe("interval.tick", function () {
            const snapshot = rtsBridge.getActors();
            if (!snapshot || !/^[0-9a-f]{32}$/.test(snapshot.session)) return;
            sessionSeen.value = snapshot.session;
            if (next === 1 && !beforeAcademy && Date.now() - lastPlacement > 8000) {
                beforeAcademy = true;
                train("terran_medic", "terran_barracks");
            }
            if (next < buildings.length && !pending && (!lastPlacement
                || Date.now() - lastPlacement > (next === 1 ? 11000 : 5000))) {
                pending = true;
                const kind = buildings[next];
                place(kind, function () { next++; pending = false; });
            }
            if (next === buildings.length && !trained && Date.now() - lastPlacement > 10000) {
                trained = true;
                train("terran_medic", "terran_barracks");
                const medicRequest = request;
                train("terran_vulture", "terran_factory");
                console.log("NEXT_PROBE_DUPLICATE request=" + medicRequest);
                train("terran_medic", "terran_barracks", medicRequest);
            }
            const medic = snapshot.units.find(function (unit) {
                return unit.kind === "terran_medic" && unit.hp > 0;
            });
            const vulture = snapshot.units.find(function (unit) {
                return unit.kind === "terran_vulture" && unit.hp > 0;
            });
            const marine = snapshot.units.find(function (unit) {
                return unit.kind === "terran_marine" && unit.hp > 0;
            });
            const firebat = capture && snapshot.units.find(function (unit) {
                return unit.kind === "terran_firebat" && unit.hp > 0;
            });
            if (capture && medic && !firebatRequested) {
                firebatRequested = true;
                train("terran_firebat", "terran_barracks");
            }
            if (capture && firebat && !firebatLogged) {
                firebatLogged = true;
                console.log("NEXT_PROBE_FIREBAT id=" + firebat.id);
            }
            if (capture && medic && firebat && firebat.hp < firebat.max_hp && !healRequested) {
                healRequested = true;
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: ++request, unit_ids: [medic.id], verb: "heal", target_id: firebat.id },
                    function (result) {
                        console.log("NEXT_PROBE_HEAL_ORDER accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                    });
            }
            if (capture && medic && firebat && medic.motion === "heal"
                && firebat.hp > 20 && !healingObserved) {
                healingObserved = true;
                console.log("NEXT_PROBE_HEAL_VISUAL medic=" + medic.id
                    + " target=" + firebat.id + " hp=" + firebat.hp);
            }
            if (trained && !mixed && medic && vulture && marine
                && (!capture || firebat && healingObserved && firebat.hp >= firebat.max_hp)) {
                mixed = true;
                mixedAt = Date.now();
                const ids = [medic.id, vulture.id, marine.id];
                if (firebat) ids.push(firebat.id);
                console.log("NEXT_PROBE_ACTORS ids=" + ids.join(","));
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: ++request, unit_ids: ids, verb: "move",
                    x: vulture.x + 96, y: vulture.y + 32 }, function (result) {
                    console.log("NEXT_PROBE_MIXED_MOVE accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (capture && mixedAt && !combatOrdered && medic && vulture && marine && firebat) {
                const enemy = snapshot.units.find(function (unit) {
                    return unit.kind === "zerg_zergling" && unit.hp > 0;
                });
                if (enemy) {
                    combatOrdered = true;
                    context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                        request: ++request, unit_ids: [medic.id, vulture.id, marine.id, firebat.id],
                        verb: "attack_move", x: enemy.x, y: enemy.y }, function (result) {
                        console.log("NEXT_PROBE_COMBAT_ORDER accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                    });
                }
            }
            if (mixedAt && !academyRemovedAt && Date.now() - mixedAt > 6000) {
                academyRemovedAt = Date.now();
                const site = locations.terran_academy;
                context.executeAction("largesceneryremove", { x: site.x, y: site.y, z: site.z,
                    direction: 0, tileIndex: 0 }, function (result) {
                    console.log("NEXT_PROBE_ACADEMY_REMOVE accepted=" + !result.error);
                });
            }
            if (academyRemovedAt && !afterAcademy && Date.now() - academyRemovedAt > 6000) {
                afterAcademy = true;
                train("terran_medic", "terran_barracks");
                console.log("NEXT_PROBE_AFTER_ACADEMY request=" + request);
            }
            if (afterAcademy && !depotRemovedAt && Date.now() - academyRemovedAt > 10000) {
                depotRemovedAt = Date.now();
                const site = locations.terran_supply_depot;
                context.executeAction("largesceneryremove", { x: site.x, y: site.y, z: site.z,
                    direction: 0, tileIndex: 0 }, function (result) {
                    console.log("NEXT_PROBE_DEPOT_REMOVE accepted=" + !result.error);
                });
            }
            if (depotRemovedAt && !afterDepot && Date.now() - depotRemovedAt > 6000) {
                afterDepot = true;
                train("terran_vulture", "terran_factory");
                console.log("NEXT_PROBE_AFTER_DEPOT request=" + request);
            }
        });
    }
});
