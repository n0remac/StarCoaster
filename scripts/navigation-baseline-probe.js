/* Test-only graphical smoke route: real wall action and native Marine orders. */
registerPlugin({ name: "Navigation Baseline Probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    let phase = 0, request = 0, start = 0, issued = false, ordering = false, wallPlaced = false;
    let armed = false;
    let actorId = null, session = null, samples = 0;
    const stops = [
        { name: "under_rail", x: 592, y: 1008 },
        { name: "wall_north", x: 656, y: 1008 },
        { name: "around_end", x: 656, y: 1040 },
        { name: "wall_south", x: 608, y: 1040 },
        { name: "return", x: 528, y: 1008 }
    ];
    function wallObject() {
        const found = objectManager.getAllObjects("wall").find(function (item) {
            return item.identifier === "rct2.scenery_wall.wbr1";
        });
        return found && found.index;
    }
    function placeWall() {
        const object = wallObject();
        if (!Number.isInteger(object)) {
            console.log("NAV_BASELINE_ERROR wall_object_missing"); return;
        }
        context.executeAction("wallplace", { x: 19 * 32, y: 31 * 32, z: 128,
            object: object, edge: 1, primaryColour: 0, secondaryColour: 0,
            tertiaryColour: 0 }, function (result) {
            wallPlaced = !result.error;
            console.log("NAV_BASELINE_WALL time=" + Date.now() + " accepted=" + wallPlaced
                + " reason=" + (result.errorMessage || "ok"));
        });
    }
    function move(destination) {
        ordering = true;
        const args = { session: session, request: ++request, unit_ids: [actorId],
            verb: "move", x: destination.x, y: destination.y };
        context.queryAction("rtsbridge.marineCommand", args, function (query) {
            if (query.error) {
                ordering = false;
                console.log("NAV_BASELINE_ERROR query_" + destination.name + " " + query.errorMessage);
                return;
            }
            context.executeAction("rtsbridge.marineCommand", args, function (result) {
                ordering = false;
                console.log("NAV_BASELINE_ORDER time=" + Date.now() + " scene=" + destination.name + " actor=" + actorId
                    + " accepted=" + !result.error + " reason=" + (result.errorMessage || "ok"));
                if (!result.error) issued = true;
            });
        });
    }
    ui.registerShortcut({ id: "starcoaster.navigationBaselineStart",
        text: "Start navigation baseline smoke test", bindings: ["CTRL+SHIFT+Y"],
        callback: function () {
            if (armed) return;
            armed = true;
            start = Date.now();
            console.log("NAV_BASELINE_TRIGGER time=" + start);
        } });
    context.subscribe("interval.tick", function () {
        if (!armed) return;
        const snapshot = rtsBridge.getActors();
        if (!snapshot || !/^[0-9a-f]{32}$/.test(snapshot.session)) return;
        const marine = snapshot.units.find(function (unit) { return unit.kind === "terran_marine"; });
        if (!marine) return;
        if (!actorId) {
            session = snapshot.session; actorId = marine.id;
            console.log("NAV_BASELINE_START time=" + Date.now() + " actor=" + actorId + " x=" + marine.x + " y=" + marine.y);
        }
        if (++samples % 4 === 0)
            console.log("NAV_BASELINE_POSITION time=" + Date.now() + " scene=" + (stops[phase] || { name: "complete" }).name
                + " actor=" + actorId + " x=" + marine.x + " y=" + marine.y);
        if (!wallPlaced) {
            if (phase === 0 && Date.now() - start > 3000 && (network.players || []).length >= 3) {
                phase = -1; placeWall();
            }
            return;
        }
        if (phase < 0) { phase = 0; start = Date.now(); }
        if (phase >= stops.length || Date.now() - start < 4000) return;
        const stop = stops[phase];
        if (issued && Math.abs(marine.x - stop.x) <= 16 && Math.abs(marine.y - stop.y) <= 16) {
            console.log("NAV_BASELINE_CROSSED time=" + Date.now() + " scene=" + stop.name + " actor=" + actorId
                + " x=" + marine.x + " y=" + marine.y);
            phase++; issued = false;
            if (phase === stops.length) console.log("NAV_BASELINE_COMPLETE time=" + Date.now() + " actor=" + actorId);
        }
        if (!issued && !ordering && phase < stops.length) move(stops[phase]);
    });
}});
