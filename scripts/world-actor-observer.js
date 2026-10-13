/* Test-only read-only actor observation on the second client. */
registerPlugin({ name: "StarCoaster Actor Observer", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        var ticks = 0, last = "", lastRoster = "";
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
            var count = snapshot.units.filter(function (unit) { return unit.id === "openbw:3001"; }).length;
            var active = count > 0;
            var state = active ? "active" : "absent";
            if (state !== last) { console.log("WORLD_ACTOR_PROBE state=" + state + " count=" + count); last = state; }
        });
    }
});
