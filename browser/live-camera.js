/* Test-only local plugin: focus a live Marine and report its native actor state. */
registerPlugin({ name: "StarCoaster WASM live camera", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    let ticks = 0, ready = false, trackedId = "", lastPosition = "", screenReported = false;
    let lastSession = "";
    let focusCount = 0, marineFocus = null;
    let sweepIndex = 0;
    const sweep = typeof STARCOASTER_CAMERA_SWEEP !== "undefined" && STARCOASTER_CAMERA_SWEEP;
    const allActors = typeof STARCOASTER_CAMERA_ALL_ACTORS !== "undefined"
        && STARCOASTER_CAMERA_ALL_ACTORS;
    const noMove = typeof STARCOASTER_CAMERA_NO_MOVE !== "undefined"
        && STARCOASTER_CAMERA_NO_MOVE;
    const perfCamera = typeof STARCOASTER_PERF_CAMERA !== "undefined" ? STARCOASTER_PERF_CAMERA : "";
    const perfWorkload = typeof STARCOASTER_PERF_WORKLOAD !== "undefined" ? STARCOASTER_PERF_WORKLOAD : "";
    const perfCommandDelayMs = typeof STARCOASTER_PERF_COMMAND_DELAY_MS !== "undefined"
        ? STARCOASTER_PERF_COMMAND_DELAY_MS : 0;
    let perfRequest = 900000, perfBatch = 0, perfDirection = false;
    let perfCommandReadyAt = 0, perfLastCommandAt = 0;
    const sweepTargets = [
        { x: 1024, y: 1024, z: 128, zoom: 0 },
        { x: 1536, y: 1536, z: 128, zoom: 0 },
        { x: 2048, y: 2048, z: 128, zoom: 0 },
        { x: 1024, y: 1024, z: 128, zoom: -1 },
        { x: 1536, y: 1536, z: 128, zoom: -1 },
        { x: 2048, y: 2048, z: 128, zoom: -1 }
    ];
    context.subscribe("interval.tick", function () {
        if (network.mode !== "client" || !ui.mainViewport || !rtsBridge || ++ticks % 20 !== 1) return;
        const snapshot = rtsBridge.getActors();
        if (!snapshot || !snapshot.session || !Array.isArray(snapshot.units)) return;
        if (snapshot.session !== lastSession) {
            lastSession = snapshot.session;
            ready = false; trackedId = ""; lastPosition = ""; screenReported = false;
            focusCount = 0; marineFocus = null;
            perfCommandReadyAt = 0; perfLastCommandAt = 0;
            console.log("WASM_CAMERA_SESSION session=" + lastSession
                + " units=" + snapshot.units.length
                + " ids=" + snapshot.units.map(function (unit) { return unit.id; }).join(","));
        }
        const marine = snapshot.units.find(function (unit) {
            return unit.kind === "terran_marine" && unit.hp > 0;
        });
        if (!marine) {
            if (!ready) console.log("WASM_CAMERA_WAIT units=" + snapshot.units.length);
            return;
        }
        if (!ready) {
            ready = true;
            perfCommandReadyAt = Date.now() + perfCommandDelayMs;
            trackedId = marine.id;
            lastPosition = marine.x + "," + marine.y;
            const tile = map.getTile(Math.floor(marine.x / 32), Math.floor(marine.y / 32));
            const surface = tile && tile.getElement(0);
            const z = surface && Number.isInteger(surface.baseZ) ? surface.baseZ
                : surface && Number.isInteger(surface.baseHeight) ? surface.baseHeight * 8 : 112;
            const focus = { x: marine.x, y: marine.y, z: z };
            marineFocus = focus;
            if (!noMove) {
                ui.mainViewport.rotation = 0;
                ui.mainViewport.zoom = sweep ? sweepTargets[0].zoom : 0;
                ui.mainViewport.moveTo(perfCamera === "away" ? { x: 1800, y: 350, z: 112 } : focus);
            }
            console.log("WASM_CAMERA_READY session=" + snapshot.session
                + " units=" + snapshot.units.length + " marine=" + JSON.stringify(marine)
                + " map=" + JSON.stringify(map.size)
                + " focus=" + JSON.stringify(focus)
                + " centre=" + JSON.stringify(ui.mainViewport.getCentrePosition()));
            if (perfCamera) console.log("WASM_PERF_ENABLED " + !!rtsBridge.performanceEnabled);
        } else {
            if (!sweep && !noMove && perfCamera !== "away" && ticks % 200 === 1 && focusCount++ < 50) {
                ui.mainViewport.moveTo(marineFocus);
                const current = rtsBridge.actorScreenPosition(trackedId);
                if (focusCount <= 3 || focusCount % 10 === 0)
                    console.log("WASM_CAMERA_REFOCUS count=" + focusCount
                        + " centre=" + JSON.stringify(ui.mainViewport.getCentrePosition())
                        + " screen=" + JSON.stringify(current));
            }
            if (sweep && ticks % 200 === 1 && ++sweepIndex < sweepTargets.length) {
                const target = sweepTargets[sweepIndex];
                ui.mainViewport.zoom = target.zoom;
                ui.mainViewport.moveTo(target);
                console.log("WASM_CAMERA_SWEEP index=" + sweepIndex
                    + " focus=" + JSON.stringify(target));
            }
            const tracked = snapshot.units.find(function (unit) { return unit.id === trackedId; });
            const screen = rtsBridge.actorScreenPosition(trackedId);
            if (!screenReported && (sweep || focusCount >= 2) && screen && screen.x > 260 && screen.x < 1240
                && screen.y > 80 && screen.y < 760) {
                screenReported = true;
                console.log("WASM_ACTOR_SCREEN id=" + trackedId + " x=" + screen.x
                    + " y=" + screen.y + " scale=" + (screen.scale || 1));
                if (allActors) console.log("WASM_ACTOR_SCREENS " + JSON.stringify(snapshot.units
                    .filter(function (unit) { return unit.kind === "terran_marine" && unit.hp > 0; })
                    .map(function (unit) {
                        const position = rtsBridge.actorScreenPosition(unit.id);
                        return position && { id: unit.id, x: position.x, y: position.y };
                    }).filter(function (position) {
                        return position && position.x > 260 && position.x < 1240
                            && position.y > 80 && position.y < 760;
                    })));
            }
            if (tracked) {
                const position = tracked.x + "," + tracked.y;
                if (position !== lastPosition) {
                    lastPosition = position;
                    console.log("WASM_ACTOR_MOVED id=" + trackedId + " x=" + tracked.x
                        + " y=" + tracked.y + " hp=" + tracked.hp + " seq=" + snapshot.seq);
                }
            }
        }
        const perfIntervalMs = perfWorkload === "moving" ? 5000 : 15000;
        const perfNow = Date.now();
        if ((perfWorkload === "moving" || perfWorkload === "fighting")
            && perfNow >= perfCommandReadyAt
            && (!perfLastCommandAt || perfNow - perfLastCommandAt >= perfIntervalMs)) {
            perfLastCommandAt = perfNow;
            const marines = snapshot.units.filter(function (unit) {
                return unit.kind === "terran_marine" && unit.hp > 0;
            }).map(function (unit) { return unit.id; });
            if (marines.length) {
                const batches = perfWorkload === "fighting" ? 1 : Math.ceil(marines.length / 32);
                const batch = perfBatch++ % batches;
                if (batch === 0) perfDirection = !perfDirection;
                const request = ++perfRequest;
                const args = { session: snapshot.session, request: request,
                    unit_ids: perfWorkload === "fighting" ? marines.slice(0, 1)
                        : marines.slice(batch * 32, batch * 32 + 32), verb: "move",
                    x: perfDirection ? 950 : 500, y: perfDirection ? 1350 : 950 };
                if (rtsBridge.performanceEnabled)
                    console.log("STARCOASTER_PERF " + JSON.stringify({ source: "browser-driver", stage: "command_input",
                        mono_ms: rtsBridge.performanceNow(), session: snapshot.session,
                        request_id: request, unit_ids: args.unit_ids, verb: "move" }));
                context.executeAction("rtsbridge.marineCommand", args, function (result) {
                    if (result.error) console.log("PERF_COMMAND_REJECT request=" + request + " error=" + result.errorMessage);
                });
            }
        }
    });
}});
