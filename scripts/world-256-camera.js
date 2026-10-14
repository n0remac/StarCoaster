// Test-only graphical audit: each client watches an opposite map boundary.
registerPlugin({ name: "World 256 Camera", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    var far = false; // Recorder substitutes true for client A.
    let ticks = 0;
    context.subscribe("interval.tick", function () {
        if (!ui.mainViewport || rtsBridge.getActors().units.length < 3 || ++ticks % 20 !== 1) return;
        const tile = far ? 247 : 8;
        const marker = map.getTile(tile, tile);
        const elements = [];
        for (let i = 0; i < marker.numElements; i++) elements.push(marker.getElement(i).type);
        ui.mainViewport.zoom = 1;
        ui.mainViewport.moveTo({ x: tile * 32 + 16, y: tile * 32 + 16, z: 112 });
        console.log("WORLD256_CAMERA boundary=" + (far ? "far" : "near") + " tile=" + tile
            + " centre=" + JSON.stringify(ui.mainViewport.getCentrePosition())
            + " zoom=" + ui.mainViewport.zoom + " elements=" + elements.join(","));
    });
}});
