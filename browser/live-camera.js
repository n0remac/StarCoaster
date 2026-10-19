/* Test-only local plugin: focus a live Marine and report its native actor state. */
registerPlugin({ name: "StarCoaster WASM live camera", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    let ticks = 0, ready = false, trackedId = "", lastPosition = "", screenReported = false;
    let focusCount = 0, marineFocus = null;
    let sweepIndex = 0;
    const sweep = typeof STARCOASTER_CAMERA_SWEEP !== "undefined" && STARCOASTER_CAMERA_SWEEP;
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
        const marine = snapshot.units.find(function (unit) {
            return unit.kind === "terran_marine" && unit.hp > 0;
        });
        if (!marine) {
            if (!ready) console.log("WASM_CAMERA_WAIT units=" + snapshot.units.length);
            return;
        }
        if (!ready) {
            ready = true;
            trackedId = marine.id;
            lastPosition = marine.x + "," + marine.y;
            const tile = map.getTile(Math.floor(marine.x / 32), Math.floor(marine.y / 32));
            const surface = tile && tile.getElement(0);
            const z = surface && Number.isInteger(surface.baseZ) ? surface.baseZ
                : surface && Number.isInteger(surface.baseHeight) ? surface.baseHeight * 8 : 112;
            const focus = { x: marine.x, y: marine.y, z: z };
            marineFocus = focus;
            ui.mainViewport.rotation = 0;
            ui.mainViewport.zoom = sweep ? sweepTargets[0].zoom : 0;
            ui.mainViewport.moveTo(focus);
            console.log("WASM_CAMERA_READY session=" + snapshot.session
                + " units=" + snapshot.units.length + " marine=" + JSON.stringify(marine)
                + " map=" + JSON.stringify(map.size)
                + " focus=" + JSON.stringify(focus)
                + " centre=" + JSON.stringify(ui.mainViewport.getCentrePosition()));
        } else {
            if (!sweep && ticks % 200 === 1 && focusCount++ < 50) {
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
    });
}});
