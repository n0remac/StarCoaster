// Test-only client observation of authoritative multiplayer park changes.
registerPlugin({ name: "Frontier Park Sync Probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    let previous = "", ticks = 0;
    context.subscribe("interval.tick", function () {
        if (++ticks % 12 !== 0) return;
        const tile = map.getTile(28, 35);
        let gate = false;
        for (let i = 0; i < tile.numElements; i++) {
            const element = tile.getElement(i);
            if (element.type === "wall" && element.object === 31) gate = true;
        }
        const state = "carousel=" + !!map.getRide(0) + " gate=" + gate;
        if (state !== previous) {
            previous = state;
            console.log("FRONTIER_PARK_STATE " + state);
        }
    });
}});
