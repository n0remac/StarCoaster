/* Read-only actor audit with one optional Marine victory order. */
registerPlugin({ name: "Frontier Lifecycle Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        var ticks = 0, sent = false, last = "";
        context.subscribe("interval.tick", function () {
            if (++ticks % 10 !== 0) return;
            var snapshot = rtsBridge.getActors();
            if (!snapshot || !snapshot.session || !Array.isArray(snapshot.units)) return;
            var marines = snapshot.units.filter(function (unit) { return unit.kind === "terran_marine" && unit.hp > 0; });
            var zerglings = snapshot.units.filter(function (unit) { return unit.kind === "zerg_zergling" && unit.hp > 0; });
            var unique = new Set(snapshot.units.map(function (unit) { return unit.id; })).size;
            var summary = snapshot.session + " marines=" + marines.length + " zerglings=" + zerglings.length
                + " unique=" + unique;
            if (summary !== last) { console.log("LIFECYCLE_ACTORS " + summary); last = summary; }
            if (!LIFECYCLE_COMMANDER || sent || marines.length !== 6 || zerglings.length !== 1) return;
            var target = zerglings[0].id;
            context.executeAction("rtsbridge.marineCommand", {
                session: snapshot.session, request: 9001,
                unit_ids: marines.map(function (unit) { return unit.id; }),
                verb: "attack", target_id: target
            }, function (result) {
                sent = !result.error;
                console.log("LIFECYCLE_ATTACK accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
            });
        });
    }
});
