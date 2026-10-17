/* Test-only two-angle camera for native mixed Zerg wave captures. */
registerPlugin({ name: "Mixed Zerg capture camera", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    let ticks = 0, announced = false;
    context.subscribe("interval.tick", function () {
        if (!ui.mainViewport || !rtsBridge || ++ticks % 10 !== 1) return;
        const snapshot = rtsBridge.getActors();
        if (!snapshot || !snapshot.session || !Array.isArray(snapshot.units)) return;
        const enemies = snapshot.units.filter(function (unit) {
            return unit.hp > 0 && (unit.kind === "zerg_zergling"
                || unit.kind === "zerg_hydralisk" || unit.kind === "zerg_ultralisk")
                && /^openbw:3/.test(unit.id);
        });
        const ultralisk = enemies.find(function (unit) { return unit.kind === "zerg_ultralisk"; });
        const focus = ultralisk || enemies[0] || { x: 1200, y: 1480 };
        const tile = map.getTile(Math.floor(focus.x / 32), Math.floor(focus.y / 32));
        const surface = tile && tile.getElement(0);
        const z = surface && Number.isInteger(surface.baseZ) ? surface.baseZ
            : surface && Number.isInteger(surface.baseHeight) ? surface.baseHeight * 8 : 112;
        ui.mainViewport.rotation = typeof STARCOASTER_MIXED_SECOND_ANGLE === "undefined" ? 0 : 1;
        ui.mainViewport.zoom = 0;
        ui.mainViewport.moveTo({ x: focus.x, y: focus.y, z: z });
        if (!announced) {
            announced = true;
            console.log("MIXED_ZERG_CAMERA_READY angle=" + ui.mainViewport.rotation);
        }
    });
}});
