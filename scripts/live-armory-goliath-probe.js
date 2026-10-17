/* Test-only construction and production driver; gameplay uses the normal UI. */
registerPlugin({ name: "Armory and Goliath gameplay probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let phase = 0, pending = false, since = 0, request = 900;
        const sites = { terran_factory: { x: 112, y: 113 }, terran_armory: { x: 120, y: 113 },
            terran_supply_depot: { x: 128, y: 113 } };
        const nativeIDs = {}, locations = {};
        let goliathID = "", mixed = false, armoryRemoved = false, waveRequested = false;
        let targetID = "", hitLogged = false, attackLogged = false;
        const enemyHealth = {};
        function command(unitIDs, verb, extra, label, fixedRequest) {
            const snapshot = rtsBridge.getActors();
            const args = Object.assign({ session: snapshot.session, request: fixedRequest || ++request,
                unit_ids: unitIDs, verb: verb }, extra || {});
            context.executeAction("rtsbridge.marineCommand", args, function (result) {
                console.log("GOLIATH_PROBE_COMMAND label=" + label + " accepted=" + !result.error
                    + " request=" + args.request + " reason=" + (result.errorMessage || "ok"));
            });
            return args.request;
        }
        function train(label, fixedRequest) {
            return command([], "train", { unit_type: "terran_goliath",
                target_entity_id: nativeIDs.terran_factory }, label, fixedRequest);
        }
        function place(kind, done) {
            const object = objectManager.getAllObjects("large_scenery").find(function (item) {
                return item.identifier === "starcoaster.scenery_large." + kind;
            });
            if (!object) { console.log("GOLIATH_PROBE_ERROR missing_object=" + kind); return; }
            const anchor = sites[kind], candidates = [];
            for (let y = 105; y < 136; y++) for (let x = 106; x < 137; x++)
                candidates.push({ x: x, y: y });
            candidates.sort(function (a, b) {
                return Math.abs(a.x - anchor.x) + Math.abs(a.y - anchor.y)
                    - Math.abs(b.x - anchor.x) - Math.abs(b.y - anchor.y)
                    || a.y - b.y || a.x - b.x;
            });
            function attempt() {
                const site = candidates.shift();
                if (!site) { console.log("GOLIATH_PROBE_ERROR no_site=" + kind); return; }
                const width = kind === "terran_factory" ? 4 : 3;
                if (rtsBridge.getActors().units.some(function (unit) {
                    return unit.hp > 0 && unit.x >= (site.x - 1) * 32
                        && unit.x < (site.x + width + 1) * 32
                        && unit.y >= (site.y - 1) * 32 && unit.y < (site.y + 3) * 32;
                })) { attempt(); return; }
                const tile = map.getTile(site.x, site.y);
                let surface = null;
                for (let index = 0; index < tile.numElements; index++)
                    if (tile.getElement(index).type === "surface") surface = tile.getElement(index);
                if (!surface) { attempt(); return; }
                const args = { x: site.x * 32, y: site.y * 32,
                    z: Number.isInteger(surface.baseZ) ? surface.baseZ : surface.baseHeight * 8,
                    direction: 0, object: object.index, primaryColour: 0,
                    secondaryColour: 0, tertiaryColour: 0 };
                context.queryAction("largesceneryplace", args, function (query) {
                    if (query.error) { attempt(); return; }
                    context.executeAction("largesceneryplace", args, function (result) {
                        if (result.error) { attempt(); return; }
                        locations[kind] = args;
                        nativeIDs[kind] = "openrct2:large_scenery:" + object.index + ":"
                            + args.x + ":" + args.y + ":" + args.z + ":0#1";
                        since = Date.now();
                        console.log("GOLIATH_PROBE_PLACE type=" + kind + " accepted=true id=" + nativeIDs[kind]);
                        done();
                    });
                });
            }
            attempt();
        }
        context.subscribe("interval.tick", function () {
            const snapshot = rtsBridge.getActors();
            if (!snapshot || !/^[0-9a-f]{32}$/.test(snapshot.session) || pending) return;
            if (phase === 0) {
                pending = true;
                place("terran_factory", function () { phase = 1; pending = false; });
            } else if (phase === 1 && Date.now() - since > 8000) {
                train("without_armory");
                phase = 2; since = Date.now();
            } else if (phase === 2 && Date.now() - since > 4500) {
                pending = true;
                place("terran_armory", function () { phase = 3; pending = false; });
            } else if (phase === 3 && Date.now() - since > 4500) {
                pending = true;
                place("terran_supply_depot", function () { phase = 4; pending = false; });
            } else if (phase === 4 && Date.now() - since > 9000) {
                const id = train("with_armory");
                console.log("GOLIATH_PROBE_DUPLICATE request=" + id);
                train("duplicate", id);
                phase = 5; since = Date.now();
            }
            const goliath = snapshot.units.find(function (unit) {
                return unit.kind === "terran_goliath" && unit.hp > 0;
            });
            const marine = snapshot.units.find(function (unit) {
                return unit.kind === "terran_marine" && unit.hp > 0;
            });
            if (phase >= 5 && goliath && !goliathID) {
                goliathID = goliath.id;
                console.log("GOLIATH_PROBE_ACTOR id=" + goliathID + " hp=" + goliath.hp);
            }
            if (goliath && goliath.attack_frames > 0 && !attackLogged) {
                attackLogged = true;
                console.log("GOLIATH_PROBE_ATTACK id=" + goliath.id
                    + " frames=" + goliath.attack_frames);
            }
            if (targetID && !hitLogged) snapshot.units.forEach(function (unit) {
                if (unit.kind !== "zerg_zergling" || enemyHealth[unit.id] === undefined) return;
                if (unit.hp < enemyHealth[unit.id]) {
                    hitLogged = true;
                    console.log("GOLIATH_PROBE_HIT target=" + unit.id
                        + " before=" + enemyHealth[unit.id] + " after=" + unit.hp);
                }
            });
            if (phase === 5 && goliath && marine && !mixed) {
                mixed = true;
                command([goliath.id, marine.id], "move", { x: goliath.x + 96,
                    y: goliath.y + 32 }, "mixed_move");
                phase = 6; since = Date.now();
            }
            if (phase === 6 && Date.now() - since > 5500 && !waveRequested) {
                waveRequested = true;
                const number = ++request;
                context.executeAction("rtsbridge.requestWave", { session: snapshot.session,
                    request: number, request_id: snapshot.session + ":wave:"
                        + network.currentPlayer.id + ":" + number }, function (result) {
                    console.log("GOLIATH_PROBE_WAVE accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            if (phase === 6 && waveRequested && Date.now() - since > 7000) {
                const enemy = snapshot.units.find(function (unit) {
                    return unit.kind === "zerg_zergling" && unit.hp > 0;
                });
                if (enemy && goliath && marine) {
                    targetID = enemy.id;
                    snapshot.units.forEach(function (unit) {
                        if (unit.kind === "zerg_zergling") enemyHealth[unit.id] = unit.hp;
                    });
                    command([goliath.id], "attack",
                        { target_id: enemy.id }, "goliath_attack");
                    phase = 7; since = Date.now();
                }
            }
            if (phase === 7 && (hitLogged || Date.now() - since > 65000) && !armoryRemoved) {
                armoryRemoved = true;
                const site = locations.terran_armory;
                context.executeAction("largesceneryremove", { x: site.x, y: site.y, z: site.z,
                    direction: 0, tileIndex: 0 }, function (result) {
                    console.log("GOLIATH_PROBE_REMOVE accepted=" + !result.error);
                });
                phase = 8; since = Date.now();
            }
            if (phase === 8 && Date.now() - since > 7000) {
                train("after_armory_removal");
                console.log("GOLIATH_PROBE_DONE id=" + goliathID);
                phase = 9;
            }
        });
    }
});
