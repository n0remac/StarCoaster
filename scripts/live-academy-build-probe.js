/* Test-only Academy placement through the ordinary large-scenery action. */
registerPlugin({ name: "Academy build probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let attempted = false;
        context.subscribe("interval.tick", function () {
            if (attempted || !rtsBridge.getActors().session) return;
            const object = objectManager.getAllObjects("large_scenery").find(function (item) {
                return item.identifier === "starcoaster.scenery_large.terran_academy";
            });
            if (!object) return;
            attempted = true;
            const sites = [];
            for (let y = 104; y < 120; y++) for (let x = 105; x < 120; x++)
                sites.push({ x: x, y: y });
            function tryNext() {
                const site = sites.shift();
                if (!site) { console.log("ACADEMY_BUILD_PROBE_ERROR no_clear_site"); return; }
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
                        console.log("ACADEMY_BUILD_PROBE_RESULT accepted=" + !result.error
                            + " x=" + args.x + " y=" + args.y + " z=" + args.z
                            + " object=" + object.index + " reason=" + (result.errorMessage || "ok"));
                    });
                });
            }
            tryNext();
        });
    }
});
