/* Isolated native graphical probe. Orders flow through the player action. */
registerPlugin({ name: "Economy E3 client probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client" || typeof ui === "undefined") return;
    const observeOnly = typeof STARCOASTER_ECONOMY_E3_OBSERVE_ONLY !== "undefined"
        && STARCOASTER_ECONOMY_E3_OBSERVE_ONLY;
    let ticks = 0, moved = false, building = false, attempts = 0, visible = false;
    context.subscribe("interval.tick", function () {
        const state = rtsBridge.getActors();
        if (!state || !state.session || !state.units) return;
        ++ticks;
        const workers = state.units.filter(function (unit) {
            return unit.alive !== false && unit.kind === "terran_scv";
        });
        if (ticks % 100 === 1) {
            if (ui.mainViewport) {
                ui.mainViewport.rotation = 0; ui.mainViewport.zoom = 0;
                ui.mainViewport.moveTo({ x: 38 * 32, y: 9 * 32, z: 112 });
            }
            console.log("ECONOMY_E3_WORKERS tick=" + ticks + " " + JSON.stringify(workers));
        }
        if (!workers.length) return;
        if (!visible && ticks % 20 === 1) {
            const object = objectManager.getAllObjects("large_scenery").find(function (item) {
                return item.identifier === "starcoaster.scenery_large.terran_supply_depot";
            });
            if (object) {
                const tile = map.getTile(34, 10);
                for (let i = 0; i < tile.numElements; ++i) {
                    const element = tile.getElement(i);
                    if (element.type === "large_scenery" && element.object === object.index) {
                        visible = true;
                        console.log("ECONOMY_E3_DEPOT_VISIBLE tile=34,10");
                        break;
                    }
                }
            }
        }
        const worker = workers[0];
        if (!observeOnly && !moved && ticks > 50) {
            moved = true;
            context.executeAction("rtsbridge.marineCommand", { session: state.session,
                request: 93001, unit_ids: [worker.id], verb: "move",
                x: 38 * 32, y: 10 * 32 }, function (result) {
                console.log("ECONOMY_E3_MOVE accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
            });
        }
        if (!observeOnly && !building && ticks > 900 && ticks % 80 === 1 && attempts < 1) {
            const request = 93100 + attempts++;
            context.executeAction("rtsbridge.marineCommand", { session: state.session,
                request: request, unit_ids: [worker.id], verb: "build",
                building_type: "terran_supply_depot", tile_x: 34, tile_y: 10 }, function (result) {
                if (!result.error) building = true;
                console.log("ECONOMY_E3_BUILD request=" + request + " accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
            });
        }
    });
}});
