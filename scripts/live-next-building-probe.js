/* Test-only placement of a catalog building through ordinary park construction. */
registerPlugin({ name: "Next building probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        const identifier = "starcoaster.scenery_large.__BUILDING__";
        let attempted = false;
        context.subscribe("interval.tick", function () {
            if (attempted || !rtsBridge.getActors().session) return;
            const object = objectManager.getAllObjects("large_scenery").find(function (item) {
                return item.identifier === identifier;
            });
            if (!object) return;
            attempted = true;
            const sites = [];
            for (let y = 104; y < 120; y++) for (let x = 105; x < 120; x++)
                sites.push({ x: x, y: y });
            function tryNext() {
                const site = sites.shift();
                if (!site) { console.log("NEXT_BUILD_PROBE_ERROR no_clear_site"); return; }
                const tile = map.getTile(site.x, site.y);
                let surface = null;
                for (let i = 0; i < tile.numElements; i++)
                    if (tile.getElement(i).type === "surface") surface = tile.getElement(i);
                if (!surface) { tryNext(); return; }
                const args = { x: site.x * 32, y: site.y * 32,
                    z: Number.isInteger(surface.baseZ) ? surface.baseZ : surface.baseHeight * 8,
                    direction: 0, object: object.index,
                    primaryColour: 0, secondaryColour: 0, tertiaryColour: 0 };
                context.queryAction("largesceneryplace", args, function (query) {
                    if (query.error) { tryNext(); return; }
                    context.executeAction("largesceneryplace", args, function (result) {
                        console.log("NEXT_BUILD_PROBE_RESULT building=__BUILDING__ accepted=" + !result.error
                            + " x=" + args.x + " y=" + args.y + " object=" + object.index
                            + " reason=" + (result.errorMessage || "ok"));
                    });
                });
            }
            tryNext();
        });
    }
});
