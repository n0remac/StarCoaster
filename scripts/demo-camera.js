/* Local-only camera helper for visual captures. No game state is changed. */
registerPlugin({
    name: "RTS Bridge Demo Camera",
    version: "1.0.0",
    authors: ["Passthrough RTS project"],
    type: "local",
    licence: "MIT",
    targetApiVersion: 124,
    minApiVersion: 124,
    main: function () {
        var demoRotation = 0;
        var cycleRotations = false;
        var ticks = 0;
        context.subscribe("interval.tick", function () {
            if (network.mode !== "client" || !ui.mainViewport) return;
            ++ticks;
            if (ticks === 40) {
                ui.mainViewport.zoom = -1;
                ui.mainViewport.rotation = demoRotation;
                ui.mainViewport.moveTo({ x: 480, y: 480 });
                console.log("RTS Bridge demo camera centred at world (480,480), rotation=" + demoRotation);
            } else if (cycleRotations && ticks > 40 && (ticks - 40) % 120 === 0) {
                demoRotation = (demoRotation + 1) % 4;
                ui.mainViewport.rotation = demoRotation;
                ui.mainViewport.moveTo({ x: 480, y: 480 });
                console.log("RTS Bridge demo camera rotation=" + demoRotation);
            }
        });
    }
});
