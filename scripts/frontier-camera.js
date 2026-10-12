/* Local viewport audit for the four OpenRCT2 camera rotations. */
registerPlugin({ name: "Frontier Camera Audit", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        var ticks = 0, rotation = -1;
        context.subscribe("interval.tick", function () {
            if (!ui.mainViewport) return;
            ticks++;
            if (ticks === 40 || (ticks > 40 && (ticks - 40) % 100 === 0)) {
                rotation = (rotation + 1) % 4;
                ui.mainViewport.rotation = rotation;
                console.log("FRONTIER_CAMERA rotation=" + rotation);
            }
        });
    }
});
