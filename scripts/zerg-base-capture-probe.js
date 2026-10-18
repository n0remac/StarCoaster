/* Test-only two-client base, wave, Marine combat, and camera evidence. */
registerPlugin({ name: "Zerg base capture probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        const driver = typeof STARCOASTER_ZERG_BASE_DRIVER !== "undefined" && STARCOASTER_ZERG_BASE_DRIVER;
        const lifecycle = typeof STARCOASTER_ZERG_BASE_LIFECYCLE !== "undefined"
            && STARCOASTER_ZERG_BASE_LIFECYCLE;
        console.log("ZERG_BASE_MODE driver=" + driver + " lifecycle=" + lifecycle);
        const structures = [
            { id: "scenario:western-spawning-pool", type: "zerg_spawning_pool", x: 8, y: 37, z: 112 },
            { id: "scenario:western-hatchery", type: "zerg_hatchery", x: 8, y: 31, z: 112 }
        ];
        const lastHealth = {}, lastPresence = {};
        let started = 0, ticks = 0, request = 5000, wave = 0, nextWave = 5;
        let waveRequestID = "", waveRequestedAt = 0;
        let spawnRequested = false, moved = false, attackedPool = false, attackedHatchery = false;
        let lastAttack = 0, mixedLogged = false;
        function present(structure) {
            const object = objectManager.getAllObjects("large_scenery").find(function (item) {
                return item.identifier === "starcoaster.scenery_large." + structure.type;
            });
            if (!object) return false;
            const tile = map.getTile(structure.x, structure.y);
            for (let i = 0; i < tile.numElements; i++) {
                const element = tile.getElement(i);
                if (element.type === "large_scenery" && element.object === object.index
                    && element.baseHeight * 8 === structure.z) return true;
            }
            return false;
        }
        function command(snapshot, units, verb, extra, label) {
            const args = Object.assign({ session: snapshot.session, request: ++request,
                unit_ids: units.map(function (unit) { return unit.id; }), verb: verb }, extra);
            context.executeAction("rtsbridge.marineCommand", args, function (result) {
                console.log("ZERG_BASE_COMMAND label=" + label + " accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
            });
        }
        context.subscribe("action.execute", function (event) {
            if (!event || !event.args || !event.result || event.result.error) return;
            const args = event.args;
            if (event.action === "rtsbridge.buildingState" && /^scenario:western-/.test(args.id || "")
                && lastHealth[args.id] !== args.health) {
                lastHealth[args.id] = args.health;
                console.log("ZERG_BASE_HEALTH id=" + args.id + " owner=" + args.owner
                    + " hp=" + args.health + " native=" + args.native_id);
            }
            if (event.action === "rtsbridge.spawnStatus" && /^.*:zerg-base:marines$/.test(args.request_id || ""))
                console.log("ZERG_BASE_SPAWN state=" + args.state + " reason=" + args.reason);
            if (event.action === "rtsbridge.waveStatus" && args.request_id === waveRequestID) {
                console.log("ZERG_BASE_WAVE state=" + args.state + " id=" + args.wave_id);
                waveRequestID = "";
                if (args.state === "queued") {
                    wave++;
                    nextWave = (Date.now() - started) / 1000 + 17;
                } else nextWave = (Date.now() - started) / 1000 + 5;
            }
        });
        context.subscribe("interval.tick", function () {
            if (++ticks % 20 === 1) {
                structures.forEach(function (structure) {
                    const visible = present(structure);
                    if (lastPresence[structure.id] !== visible) {
                        lastPresence[structure.id] = visible;
                        console.log("ZERG_BASE_PRESENT id=" + structure.id + " present=" + visible);
                    }
                });
            }
            if (!rtsBridge || !rtsBridge.getActors().session) {
                if (driver && ticks % 200 === 1)
                    console.log("ZERG_BASE_WAIT_ACTORS ticks=" + ticks);
                return;
            }
            if (!started) started = Date.now();
            const seconds = (Date.now() - started) / 1000, snapshot = rtsBridge.getActors();
            if (driver && ticks % 200 === 1)
                console.log("ZERG_BASE_CLOCK seconds=" + seconds + " units=" + snapshot.units.length);
            if (ticks % 20 === 1) {
                if (typeof ui !== "undefined" && ui.mainViewport) {
                    const mixed = seconds >= 36 && seconds < 53;
                    const enemy = mixed && snapshot.units.find(function (unit) {
                        return unit.kind === "zerg_hydralisk" && unit.hp > 0;
                    });
                    ui.mainViewport.rotation = 0;
                    ui.mainViewport.zoom = 0;
                    ui.mainViewport.moveTo(enemy
                        ? { x: enemy.x, y: enemy.y, z: 112 }
                        : { x: 15 * 32, y: 35 * 32, z: 112 });
                }
            }
            if (snapshot.units.some(function (unit) { return unit.kind === "zerg_hydralisk" && unit.hp > 0; })
                && snapshot.units.some(function (unit) { return unit.kind === "zerg_zergling" && unit.hp > 0; })
                && !mixedLogged) {
                mixedLogged = true;
                console.log("ZERG_BASE_MIXED_WAVE visible=true");
            }
            if (!driver) return;
            if (waveRequestID && Date.now() - waveRequestedAt > 15000) {
                waveRequestID = "";
                nextWave = seconds + 5;
            }
            if (!lifecycle && wave < 4 && !waveRequestID && seconds >= nextWave) {
                const number = ++request;
                const id = snapshot.session + ":wave:" + network.currentPlayer.id + ":" + number;
                waveRequestID = id;
                waveRequestedAt = Date.now();
                context.executeAction("rtsbridge.requestWave", { session: snapshot.session,
                    request: number, request_id: id }, function (result) {
                    console.log("ZERG_BASE_WAVE_REQUEST accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                    if (result.error && waveRequestID === id) {
                        waveRequestID = "";
                        nextWave = (Date.now() - started) / 1000 + 5;
                    }
                });
            }
            if (!spawnRequested && seconds >= (lifecycle ? 5 : 55)) {
                spawnRequested = true;
                context.executeAction("rtsbridge.spawnMarine", { session: snapshot.session,
                    request_id: snapshot.session + ":zerg-base:marines", count: 5,
                    x: 20 * 32, y: 38 * 32 }, function (result) {
                    console.log("ZERG_BASE_SPAWN_REQUEST accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                });
            }
            const marines = snapshot.units.filter(function (unit) {
                return unit.kind === "terran_marine" && unit.hp > 0
                    && /^openbw:3/.test(unit.id) && unit.x < 1000 && unit.y < 1700;
            });
            if (marines.length >= 3 && !moved) {
                moved = true;
                console.log("ZERG_BASE_MARINES count=" + marines.length + " x=" + marines[0].x);
                command(snapshot, marines, "move", { x: 17 * 32, y: 38 * 32 }, "approach_base");
            }
            if (!moved || seconds < (lifecycle ? 11 : 61) || marines.length < 1) return;
            const target = present(structures[0]) ? structures[0]
                : !lifecycle && present(structures[1]) ? structures[1] : null;
            if (!target || Date.now() - lastAttack < 8000) return;
            lastAttack = Date.now();
            if (target === structures[0]) attackedPool = true;
            else attackedHatchery = true;
            command(snapshot, marines, "attack", { target_entity_id: target.id },
                target === structures[0] ? "spawning_pool" : "hatchery");
            if (attackedPool && attackedHatchery)
                console.log("ZERG_BASE_BOTH_ATTACKED true");
        });
    }
});
