/* Test-only client probe. Uses the same synchronized action as Load Park UI. */
registerPlugin({ name: "StarCoaster park switch probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    var scenario = null, catalog = null, readyAt = 0, cameraAt = 0;
    var requested = false, menuSeen = false;
    var target = typeof PARK_SWITCH_PROBE_TARGET === "string" ? PARK_SWITCH_PROBE_TARGET : "";
    var delay = typeof PARK_SWITCH_PROBE_DELAY_MS === "number" ? PARK_SWITCH_PROBE_DELAY_MS : 90000;
    context.subscribe("action.execute", function (event) {
        if (event.action === "rtsbridge.scenarioStatus") scenario = event.args;
        if (event.action === "rtsbridge.parkCatalog") catalog = event.args;
    });
    context.subscribe("interval.tick", function () {
        if (network.mode !== "client" || !scenario || !catalog || catalog.phase !== "ready"
            || scenario.session !== rtsBridge.getActors().session) return;
        if (!readyAt) {
            readyAt = Date.now();
            console.log("PARK_SWITCH_BROWSER_READY park=" + catalog.current
                + " generation=" + catalog.generation + " session=" + scenario.session
                + " units=" + rtsBridge.getActors().units.length);
        }
        if (!menuSeen && ui.getWindow("starcoaster-load-park")) {
            menuSeen = true;
            console.log("PARK_SWITCH_MENU_VISIBLE park=" + catalog.current);
        }
        if (requested || catalog.current === target || !catalog.parks.includes(target)
            || scenario.commander_player !== network.currentPlayer.id
            || Date.now() - readyAt < delay) return;
        if (!cameraAt) {
            var units = rtsBridge.getActors().units;
            var actor = units.find(function (unit) { return unit.kind === "terran_marine" && unit.hp > 0; })
                || units.find(function (unit) { return unit.hp > 0; });
            if (!actor || !ui.mainViewport) return;
            var tile = map.getTile(Math.floor(actor.x / 32), Math.floor(actor.y / 32));
            var surface = tile && tile.getElement(0);
            var z = surface && Number.isInteger(surface.baseZ) ? surface.baseZ : 112;
            ui.mainViewport.rotation = 0;
            ui.mainViewport.zoom = 0;
            ui.mainViewport.moveTo({ x: actor.x, y: actor.y, z: z });
            cameraAt = Date.now();
            console.log("PARK_SWITCH_CAMERA_FOCUS kind=" + actor.kind + " id=" + actor.id);
            return;
        }
        if (Date.now() - cameraAt < 3000) return;
        requested = true;
        console.log("PARK_SWITCH_BROWSER_BEFORE units=" + rtsBridge.getActors().units.length);
        context.executeAction("rtsbridge.loadPark", { session: scenario.session,
            generation: catalog.generation, park: target, decision: "discard" }, function (result) {
            console.log("PARK_SWITCH_BROWSER_REQUEST accepted=" + !result.error
                + " reason=" + (result.errorMessage || "ok"));
        });
    });
} });
