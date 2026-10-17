/* Test-only fixed camera for the Mt. Zergling next-tech capture. */
registerPlugin({ name: "Medic and Vulture production camera", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    let ticks = 0, announced = false, closeEffect = false;
    context.subscribe("interval.tick", function () {
        if (!ui.mainViewport || !rtsBridge.getActors().session || ++ticks % 10 !== 1) return;
        const actors = rtsBridge.getActors().units;
        const firebat = actors.find(function (unit) {
            return unit.kind === "terran_firebat" && unit.hp > 0;
        });
        if ((firebat && firebat.motion === "attack" && firebat.attack_frames > 0)
            || actors.some(function (unit) { return unit.kind === "terran_medic"
                && unit.motion === "heal"; })) closeEffect = true;
        const focus = firebat || { x: 3520, y: 3616 };
        const tile = map.getTile(Math.floor(focus.x / 32), Math.floor(focus.y / 32));
        const surface = tile && tile.getElement(0);
        const z = surface && Number.isInteger(surface.baseZ) ? surface.baseZ
            : surface && Number.isInteger(surface.baseHeight) ? surface.baseHeight * 8 : 1216;
        ui.mainViewport.rotation = 0;
        ui.mainViewport.zoom = closeEffect ? -1 : 0;
        ui.mainViewport.moveTo({ x: focus.x, y: focus.y, z: z });
        if (!announced) {
            announced = true;
            console.log("MEDIC_VULTURE_CAMERA_READY");
        }
    });
}});
