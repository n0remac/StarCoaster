/* Test-only fixed camera for the Mt. Zergling production capture. */
registerPlugin({ name: "Barracks production camera", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    let ticks = 0, announced = false;
    context.subscribe("interval.tick", function () {
        if (!ui.mainViewport || !rtsBridge.getActors().session || ++ticks % 20 !== 1) return;
        ui.mainViewport.rotation = 0;
        ui.mainViewport.zoom = 0;
        ui.mainViewport.moveTo({ x: 3264, y: 3376, z: 1216 });
        if (!announced) {
            announced = true;
            console.log("BARRACKS_PRODUCTION_CAMERA_READY");
        }
    });
}});
