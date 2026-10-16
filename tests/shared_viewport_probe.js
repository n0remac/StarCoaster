// Test-only native park entity and viewport-input probe, installed on host and client.
registerPlugin({ name: "Shared Viewport Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        // Frontier's generated park has no guest spawns. Add one to an existing
        // path in this disposable test session, through synchronized actions.
        context.registerAction("viewportprobe.prepare", function () { return {}; }, function (event) {
            const tile = map.getTile(event.args.x / 32, event.args.y / 32);
            for (let i = 0; i < tile.numElements; i++) {
                const item = tile.getElement(i);
                if (item.type === "surface") item.ownership = 0;
            }
            cheats.sandboxMode = true;
            return {};
        });
        context.registerAction("viewportprobe.guest", function () { return {}; }, function () {
            const guest = park.generateGuest();
            console.log("PARK_INPUT_GUEST created=" + !!guest);
            return {};
        });
        context.registerAction("viewportprobe.overlap", function () { return {}; }, function () {
            const marine = rtsBridge.getActors().units.find(function (unit) { return unit.id === "openbw:1000"; });
            const guest = map.getAllEntities("guest")[0];
            guest.x = marine.x; guest.y = marine.y;
            guest.z = map.getTile(Math.floor(marine.x / 32), Math.floor(marine.y / 32)).getElement(0).baseZ;
            return {};
        });
        let requested = false;
        if (network.mode === "server") {
            context.subscribe("interval.tick", function () {
                if (!requested && rtsBridge.getActors().units.length) {
                    requested = true;
                    for (let y = 6; y < map.size.y - 6; y++) for (let x = 6; x < map.size.x - 6; x++) {
                        const tile = map.getTile(x, y);
                        for (let i = 0; i < tile.numElements; i++) {
                            const path = tile.getElement(i);
                            if (path.type !== "footpath") continue;
                            const args = { x: x * 32, y: y * 32, z: path.baseZ, direction: 0 };
                            context.executeAction("viewportprobe.prepare", args, function () {
                                context.executeAction("peepspawnplace", args, function (result) {
                                    if (result.error) throw new Error("guest spawn: " + result.errorMessage);
                                    context.executeAction("viewportprobe.guest", {}, function () {});
                                });
                            });
                            return;
                        }
                    }
                    throw new Error("no path for guest fixture");
                }
            });
            return;
        }
        if (typeof ui === "undefined") return;
        let toolClicks = 0, report = 0;
        function closeNativeWindows() {
            for (let i = ui.windows - 1; i >= 0; i--) {
                const window = ui.getWindow(i);
                if (window.classification === 12 || window.classification === 23) window.close();
            }
        }
        function focus(point) {
            ui.mainViewport.rotation = 0; ui.mainViewport.zoom = 0;
            ui.mainViewport.moveTo(point);
        }
        function project(point) {
            return { x: point.y - point.x - ui.mainViewport.left,
                y: (point.x + point.y) / 2 - point.z - ui.mainViewport.top - 10 };
        }
        function emit(kind, point) {
            const windows = [];
            for (let i = 0; i < ui.windows; i++) windows.push(ui.getWindow(i).classification);
            console.log("PARK_INPUT_REPORT " + JSON.stringify({ report: ++report, kind: kind,
                point: point, windows: windows, tool: ui.tool ? ui.tool.id : null, toolClicks: toolClicks }));
        }
        function shortcut(id, key, callback) {
            ui.registerShortcut({ id: "viewportprobe." + id, text: "Test shared viewport " + id,
                bindings: ["CTRL+SHIFT+" + key], callback: callback });
        }
        shortcut("marine", "1", function () {
            closeNativeWindows();
            const marine = rtsBridge.getActors().units.find(function (unit) { return unit.id === "openbw:1000"; });
            if (!marine) throw new Error("missing Marine");
            const tile = map.getTile(Math.floor(marine.x / 32), Math.floor(marine.y / 32));
            const ground = tile.getElement(0);
            focus({ x: marine.x, y: marine.y, z: ground.baseZ });
            const screen = rtsBridge.actorScreenPosition(marine.id);
            emit("marine", { x: screen.x, y: screen.y - 12 });
        });
        shortcut("ride", "2", function () {
            closeNativeWindows();
            const ride = map.rides.find(function (item) { return item.name === "Frontier Carousel"; });
            for (let y = 0; y < map.size.y; y++) for (let x = 0; x < map.size.x; x++) {
                const tile = map.getTile(x, y);
                for (let i = 0; i < tile.numElements; i++) {
                    const item = tile.getElement(i);
                    if (item.type === "track" && item.ride === ride.id) {
                        const point = { x: x * 32 + 16, y: y * 32 + 16, z: item.baseZ };
                        focus(point); emit("ride", project(point)); return;
                    }
                }
            }
            throw new Error("missing carousel track");
        });
        shortcut("guest", "3", function () {
            closeNativeWindows();
            const guest = map.getAllEntities("guest")[0];
            if (!guest) throw new Error("missing generated guest");
            focus(guest); emit("guest", project(guest));
        });
        shortcut("tool", "4", function () {
            closeNativeWindows();
            ui.activateTool({ id: "viewportprobe.construction", cursor: "dig_down",
                onDown: function () { toolClicks++; } });
            emit("tool", { x: 640, y: 400 });
        });
        shortcut("overlap", "6", function () {
            closeNativeWindows();
            context.executeAction("viewportprobe.overlap", {}, function (result) {
                if (result.error) throw new Error(result.errorMessage);
                const marine = rtsBridge.getActors().units.find(function (unit) { return unit.id === "openbw:1000"; });
                const z = map.getTile(Math.floor(marine.x / 32), Math.floor(marine.y / 32)).getElement(0).baseZ;
                focus({ x: marine.x, y: marine.y, z: z });
                const screen = rtsBridge.actorScreenPosition(marine.id);
                emit("overlap", { x: screen.x, y: screen.y - 12 });
            });
        });
        shortcut("report", "5", function () { emit("state", null); });
    }
});
