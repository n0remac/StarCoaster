/* Test-only fixed viewport for the layered navigation graphical smoke test. */
registerPlugin({ name: "Navigation Baseline Camera", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    var baselineRotation = 0;
    let ticks = 0;
    context.subscribe("interval.tick", function () {
        if (!ui.mainViewport || !rtsBridge.getActors().units.length || ++ticks % 20 !== 1) return;
        ui.mainViewport.rotation = baselineRotation;
        ui.mainViewport.zoom = -1;
        ui.mainViewport.moveTo({ x: 19 * 32 + 16, y: 31 * 32 + 16, z: 128 });
        console.log("NAV_BASELINE_CAMERA time=" + Date.now() + " rotation=" + baselineRotation
            + " centre=" + JSON.stringify(ui.mainViewport.getCentrePosition())
            + " zoom=" + ui.mainViewport.zoom);
    });
}});
