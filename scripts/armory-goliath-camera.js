/* Test-only camera for two-client Armory and Goliath captures. */
registerPlugin({ name: "Armory and Goliath camera", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    let ticks = 0, ready = false, started = 0;
    context.subscribe("interval.tick", function () {
        if (!ui.mainViewport || !rtsBridge.getActors().session || ++ticks % 10 !== 1) return;
        const goliath = rtsBridge.getActors().units.find(function (unit) {
            return unit.kind === "terran_goliath" && unit.hp > 0;
        });
        const followActor = typeof STARCOASTER_ARMORY_STATIC_CAMERA === "undefined" && goliath;
        const focus = followActor || { x: 3744, y: 3648 };
        const tile = map.getTile(Math.floor(focus.x / 32), Math.floor(focus.y / 32));
        const surface = tile && tile.getElement(0);
        const z = surface && Number.isInteger(surface.baseZ) ? surface.baseZ
            : surface && Number.isInteger(surface.baseHeight) ? surface.baseHeight * 8 : 1216;
        if (!started) started = Date.now();
        ui.mainViewport.rotation = Math.floor((Date.now() - started) / 20000) % 4;
        ui.mainViewport.zoom = followActor ? -1 : 0;
        ui.mainViewport.moveTo({ x: focus.x, y: focus.y, z: z });
        if (!ready) { ready = true; console.log("ARMORY_GOLIATH_CAMERA_READY"); }
    });
}});
