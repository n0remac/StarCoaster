// Test-only second-client target catalog and shop observer.
registerPlugin({ name: "Live Target Observer", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        let lastShop = null;
        context.subscribe("action.execute", function (event) {
            if (event.action !== "rtsbridge.targetCatalog") return;
            const args = event.args || {};
            const present = (args.targets || []).some(function (target) {
                return /^openrct2:ride:4#/.test(target.id);
            });
            if (present) console.log("LIVE_TARGET_OBSERVER_CATALOG version=" + args.version
                + " ride=true");
        });
        context.subscribe("interval.tick", function () {
            const tile = map.getTile(26, 30);
            let present = false;
            for (let index = 0; index < tile.numElements; index++) {
                const element = tile.getElement(index);
                if (element.type === "track" && element.ride === 4) present = true;
            }
            if (present !== lastShop) {
                lastShop = present;
                console.log("LIVE_TARGET_OBSERVER_SHOP present=" + present);
            }
        });
    }
});
