/* Test-only client probe for one runtime Marine and native orders. */
registerPlugin({ name: "StarCoaster Actor Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        var ticks = 0, last = "", lastRoster = "", moved = false, attacked = false;
        var checkedRemoval = false, selectedOnce = false;
        context.subscribe("interval.tick", function () {
            if (++ticks % 20 !== 0 || !rtsBridge) return;
            var snapshot = rtsBridge.getActors();
            if (!snapshot.session) return;
            var marines = snapshot.units.filter(function (unit) {
                return unit.kind === "terran_marine" && unit.hp > 0;
            }).map(function (unit) { return unit.id; }).sort();
            var roster = marines.join(",");
            if (roster !== lastRoster) {
                console.log("WORLD_ACTOR_ROSTER count=" + marines.length + " ids=" + roster);
                lastRoster = roster;
            }
            var runtime = snapshot.units.filter(function (unit) { return unit.id === "openbw:3001"; })[0];
            var count = snapshot.units.filter(function (unit) { return unit.id === "openbw:3001"; }).length;
            var state = runtime ? "active" : "absent";
            if (state !== last) {
                console.log("WORLD_ACTOR_PROBE state=" + state + " count=" + count);
                if (last === "active" && state === "absent" && !checkedRemoval) {
                    checkedRemoval = true;
                    context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                        request: 8103, unit_ids: ["openbw:3001"], verb: "hold" }, function (result) {
                            console.log("WORLD_ACTOR_POST_DEATH_QUERY accepted=" + !result.error);
                        });
                }
                last = state;
            }
            if (!runtime) return;
            if (!selectedOnce) {
                var hit = rtsBridge.hitTest(runtime.x, runtime.y, 48);
                if (hit === runtime.id) {
                    selectedOnce = true;
                    console.log("WORLD_ACTOR_SELECT id=" + hit);
                }
            }
            if (!moved) {
                moved = true;
                console.log("WORLD_ACTOR_MOVE_REQUEST");
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: 8101, unit_ids: [runtime.id], verb: "move", x: 640, y: 976 },
                    function (result) {
                        console.log("WORLD_ACTOR_MOVE_QUERY accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                    });
            } else if (!attacked && ticks > (typeof STARCOASTER_ACTOR_ATTACK_DELAY === "number"
                ? STARCOASTER_ACTOR_ATTACK_DELAY : 100)) {
                var zergling = snapshot.units.filter(function (unit) {
                    return unit.kind === "zerg_zergling" && unit.hp > 0;
                })[0];
                if (!zergling) return;
                attacked = true;
                console.log("WORLD_ACTOR_ATTACK_REQUEST target=" + zergling.id);
                context.executeAction("rtsbridge.marineCommand", { session: snapshot.session,
                    request: 8102, unit_ids: [runtime.id], verb: "attack", target_id: zergling.id },
                    function (result) {
                        console.log("WORLD_ACTOR_ATTACK_QUERY accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                    });
            }
        });
    }
});
