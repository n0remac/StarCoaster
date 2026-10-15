// Test-only second-client park state observer.
registerPlugin({ name: "Live Construction Observer", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let previous = null, ticks = 0;
        context.subscribe("interval.tick", function () {
            if (++ticks % 4) return;
            const tile = map.getTile(20, 31);
            let present = false;
            for (let index = 0; index < tile.numElements; index++)
                if (tile.getElement(index).type === "wall") present = true;
            if (present !== previous) {
                previous = present;
                console.log("LIVE_OBSERVER_WALL present=" + present);
            }
        });
    }
});
