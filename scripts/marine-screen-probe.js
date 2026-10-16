/* Test-only graphical projection and drag-selection probe. */
registerPlugin({ name: "Marine Screen Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client" || typeof ui === "undefined") return;
        let active = false, ticks = 0, phase = 0;
        ui.registerShortcut({ id: "starcoaster.screen-probe", text: "Test Marine screen projection",
            bindings: ["CTRL+SHIFT+M"], callback: function () {
                active = true;
                console.log("MARINE_SCREEN_PROBE_START");
            } });
        context.subscribe("interval.tick", function () {
            if (!active || phase >= 4 || ++ticks % 80 !== 1 || !ui.mainViewport) return;
            const snapshot = rtsBridge.getActors();
            const marine = snapshot.units.find(function (unit) { return unit.id === "openbw:1000"; });
            if (!marine) return;
            const tile = map.getTile(Math.floor(marine.x / 32), Math.floor(marine.y / 32));
            let z = 0;
            for (let index = 0; index < tile.numElements; index++) {
                const item = tile.getElement(index);
                if (item.type === "surface") z = item.baseZ === undefined ? item.baseHeight * 8 : item.baseZ;
            }
            const rotation = phase, zoom = [0, 1, 2, -1][phase];
            ui.mainViewport.rotation = rotation;
            ui.mainViewport.zoom = zoom;
            ui.mainViewport.moveTo({ x: marine.x, y: marine.y, z: z });
            const point = rtsBridge.actorScreenPosition(marine.id);
            console.log("MARINE_SCREEN_PROBE rotation=" + rotation + " zoom=" + zoom + " z=" + z
                + " x=" + (point ? point.x : -1) + " y=" + (point ? point.y : -1)
                + " tool=" + (ui.tool ? ui.tool.id : "none"));
            phase++;
        });
    }
});
