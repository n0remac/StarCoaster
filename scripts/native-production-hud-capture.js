/* Test-only camera and authenticated native production probe for the seven-building fixture. */
registerPlugin({ name: "Native production HUD capture", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client" || typeof ui === "undefined") return;
    const buildings = [
        ["Hatchery", 8, 31, 4, 3], ["Spawning Pool", 8, 37, 3, 2],
        ["Barracks", 100, 100, 4, 3], ["Academy", 106, 100, 3, 2],
        ["Supply Depot", 111, 100, 3, 2], ["Factory", 116, 100, 4, 3],
        ["Armory", 122, 100, 3, 2]
    ];
    let focus = typeof STARCOASTER_HUD_INITIAL_FOCUS === "number"
        ? STARCOASTER_HUD_INITIAL_FOCUS : 0;
    let ticks = 0, attempts = 0, request = 8000, observedEgg = false, ready = false;
    let demolitionAccepted = false, demolitionClosed = false, inspectorReported = false;
    let inspectorReadyReported = false, constructionReported = false, constructionStatus = "";
    if (typeof STARCOASTER_HUD_DRIVER !== "undefined" && STARCOASTER_HUD_DRIVER) {
        ui.registerShortcut({ id: "starcoaster.hud-gallery", text: "Next native building HUD",
            bindings: ["CTRL+SHIFT+H"], callback: function () {
                ui.closeWindows("starcoaster-building-info");
                focus = (focus + 1) % buildings.length;
                centre();
                console.log("NATIVE_HUD_FOCUS building=" + buildings[focus][0]);
            } });
        ui.registerShortcut({ id: "starcoaster.hud-demolish", text: "Demolish selected test Armory",
            bindings: ["CTRL+SHIFT+D"], callback: function () {
                if (buildings[focus][0] !== "Armory" || !ui.getWindow("starcoaster-building-info")) {
                    console.log("NATIVE_HUD_DEMOLISH_ERROR armory_inspector_required"); return;
                }
                const tile = map.getTile(122, 100);
                let scenery = null;
                for (let index = 0; index < tile.numElements; ++index) {
                    const element = tile.getElement(index);
                    if (element.type === "large_scenery") { scenery = element; break; }
                }
                if (!scenery) { console.log("NATIVE_HUD_DEMOLISH_ERROR armory_missing"); return; }
                context.executeAction("largesceneryremove", { x: 122 * 32, y: 100 * 32,
                    z: scenery.baseZ === undefined ? scenery.baseHeight * 8 : scenery.baseZ,
                    direction: scenery.rotation || 0, tileIndex: 0 }, function (result) {
                    demolitionAccepted = !result.error;
                    console.log("NATIVE_HUD_DEMOLISH accepted=" + demolitionAccepted
                        + " reason=" + (result.errorMessage || "ok"));
                });
            } });
    }
    function centre() {
        if (!ui.mainViewport) return;
        const building = buildings[focus];
        const tile = map.getTile(building[1], building[2]);
        let z = 0;
        for (let index = 0; index < tile.numElements; ++index) {
            const item = tile.getElement(index);
            if (item.type === "surface") z = item.baseZ === undefined ? item.baseHeight * 8 : item.baseZ;
        }
        ui.mainViewport.rotation = 0;
        ui.mainViewport.zoom = 0;
        ui.mainViewport.moveTo({ x: building[1] * 32 + building[3] * 16,
            y: building[2] * 32 + building[4] * 16, z: z });
    }
    context.subscribe("interval.tick", function () {
        const snapshot = rtsBridge.getActors();
        if (!snapshot.session) return;
        if (!ready) {
            ready = true;
            console.log("NATIVE_HUD_CAPTURE_READY");
        }
        if (++ticks % 20 === 1) centre();
        if (!inspectorReported && ui.getWindow("starcoaster-building-info")) {
            inspectorReported = true;
            console.log("NATIVE_HUD_INSPECTOR_OPEN building=" + buildings[focus][0]);
        }
        const inspector = ui.getWindow("starcoaster-building-info");
        const firstCommand = inspector && inspector.findWidget("building-command-0");
        if (!inspectorReadyReported && firstCommand && !firstCommand.isDisabled) {
            inspectorReadyReported = true;
            console.log("NATIVE_HUD_INSPECTOR_READY building=" + buildings[focus][0]);
        }
        if (typeof STARCOASTER_HUD_CONSTRUCTION_PROBE !== "undefined"
            && STARCOASTER_HUD_CONSTRUCTION_PROBE) {
            const construction = ui.getWindow("starcoaster-construction");
            if (construction && !constructionReported) {
                constructionReported = true;
                console.log("NATIVE_HUD_CONSTRUCTION_WINDOW x=" + construction.x
                    + " y=" + construction.y + " width=" + construction.width);
            }
            const status = construction && construction.findWidget("barracks-status");
            if (status && status.text !== constructionStatus) {
                constructionStatus = status.text;
                console.log("NATIVE_HUD_CONSTRUCTION_STATUS text=" + constructionStatus);
            }
        }
        if (typeof STARCOASTER_HUD_DRIVER === "undefined" || !STARCOASTER_HUD_DRIVER) return;
        if (demolitionAccepted && !demolitionClosed && !ui.getWindow("starcoaster-building-info")) {
            demolitionClosed = true;
            console.log("NATIVE_HUD_TARGET_CLOSED building=Armory");
        }
        if (snapshot.units.some(function (unit) { return unit.kind === "zerg_egg" && unit.hp > 0; })) {
            if (!observedEgg) console.log("NATIVE_HUD_EGG_VISIBLE");
            observedEgg = true;
        }
        if (observedEgg || attempts >= 6 || ticks % 80 !== 1
            || !snapshot.units.some(function (unit) { return unit.kind === "zerg_larva" && unit.hp > 0; })) return;
        const serial = ++request;
        ++attempts;
        context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
            request: serial, unit_ids: [], verb: "train", unit_type: "zerg_zergling",
            target_entity_id: "scenario:western-hatchery" }, function (result) {
            console.log("NATIVE_HUD_ORDER request=" + serial + " accepted=" + !result.error
                + " reason=" + (result.errorMessage || "ok"));
        });
    });
}});
