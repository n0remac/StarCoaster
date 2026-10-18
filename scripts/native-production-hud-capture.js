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
    let focus = 0, ticks = 0, attempts = 0, request = 8000, observedEgg = false, ready = false;
    if (typeof STARCOASTER_HUD_DRIVER !== "undefined" && STARCOASTER_HUD_DRIVER) {
        ui.registerShortcut({ id: "starcoaster.hud-gallery", text: "Next native building HUD",
            bindings: ["CTRL+SHIFT+H"], callback: function () {
                ui.closeWindows("starcoaster-building-info");
                focus = (focus + 1) % buildings.length;
                console.log("NATIVE_HUD_FOCUS building=" + buildings[focus][0]);
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
        if (typeof STARCOASTER_HUD_DRIVER === "undefined" || !STARCOASTER_HUD_DRIVER) return;
        if (snapshot.units.some(function (unit) { return unit.kind === "zerg_egg" && unit.alive; })) {
            if (!observedEgg) console.log("NATIVE_HUD_EGG_VISIBLE");
            observedEgg = true;
        }
        if (observedEgg || attempts >= 6 || ticks % 80 !== 1
            || !snapshot.units.some(function (unit) { return unit.kind === "zerg_larva" && unit.alive; })) return;
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
