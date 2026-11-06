/* Read-only intersection aid for authored park rights and native site scan. */
registerPlugin({ name: "Economy E3 park site scan", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    let done = false;
    const sizes = { terran_command_center: [4, 3], terran_supply_depot: [3, 2],
        terran_barracks: [4, 3], terran_academy: [3, 2], terran_factory: [4, 3],
        terran_armory: [3, 2], terran_refinery: [4, 2] };
    context.subscribe("interval.tick", function () {
        if (done) return;
        const state = rtsBridge.getActors();
        if (!state || !state.session || !state.units.length) return;
        done = true;
        const resources = state.units.filter(function (unit) {
            return unit.kind === "mineral_field" || unit.kind === "vespene_geyser";
        }).map(function (unit) {
            const width = unit.kind === "mineral_field" ? 2 : 4;
            const height = unit.kind === "mineral_field" ? 1 : 2;
            return { x: Math.floor((unit.x - width * 16) / 32),
                y: Math.floor((unit.y - height * 16) / 32), width: width, height: height };
        });
        Object.keys(sizes).forEach(function (type) {
            const width = sizes[type][0], height = sizes[type][1], candidates = [];
            for (let y = 5; y <= 19; ++y) for (let x = 18; x <= 41; ++x) {
                if (x < 24 && x + width > 20 && y < 11 && y + height > 8) continue;
                if (resources.some(function (site) {
                    return x < site.x + site.width && x + width > site.x
                        && y < site.y + site.height && y + height > site.y;
                })) continue;
                let valid = true, z = -1;
                for (let yy = y; yy < y + height && valid; ++yy)
                    for (let xx = x; xx < x + width && valid; ++xx) {
                        const tile = map.getTile(xx, yy);
                        if (!tile || tile.numElements !== 1) { valid = false; break; }
                        const surface = tile.getElement(0);
                        const heightZ = Number.isInteger(surface.baseZ)
                            ? surface.baseZ : surface.baseHeight * 8;
                        if (surface.type !== "surface" || !surface.hasConstructionRights
                            || surface.waterHeight || surface.slope || (z >= 0 && z !== heightZ))
                            valid = false;
                        z = heightZ;
                    }
                if (valid) candidates.push(x + "," + y);
            }
            console.log("ECONOMY_E3_SITE_SCAN type=" + type + " candidates="
                + candidates.slice(0, 90).join(" ") + " total=" + candidates.length);
        });
        console.log("ECONOMY_E3_SITE_SCAN_DONE");
    });
}});
