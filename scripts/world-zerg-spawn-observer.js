/* Test-only observation of scenario-spawned native Zerglings. */
registerPlugin({ name: "StarCoaster Zerg Spawn Observer", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        var ticks = 0, lastRoster = "", first = {};
        var moved = {};
        context.subscribe("interval.tick", function () {
            if (++ticks % 20 !== 0 || !rtsBridge) return;
            var snapshot = rtsBridge.getActors();
            if (!snapshot.session) return;
            var zerg = snapshot.units.filter(function (unit) {
                return unit.kind === "zerg_zergling" && unit.hp > 0;
            });
            var ids = zerg.map(function (unit) { return unit.id; }).sort();
            var roster = ids.join(",");
            if (roster !== lastRoster) {
                console.log("WORLD_ZERG_ROSTER count=" + ids.length + " ids=" + roster);
                lastRoster = roster;
            }
            zerg.forEach(function (unit) {
                if (!/^openbw:30[0-9][0-9]$/.test(unit.id)) return;
                if (!first[unit.id]) first[unit.id] = { x: unit.x, y: unit.y };
                if (!moved[unit.id] && (unit.x !== first[unit.id].x || unit.y !== first[unit.id].y)) {
                    moved[unit.id] = true;
                    console.log("WORLD_ZERG_MOVED id=" + unit.id + " x=" + unit.x + " y=" + unit.y);
                }
            });
        });
    }
});
