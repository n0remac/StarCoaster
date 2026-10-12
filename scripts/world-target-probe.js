/* Local integration fixture: command a Marine to attack an existing park ride. */
registerPlugin({ name: "World Bridge Target Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        var ticks = 0, sent = false, attempts = 0;
        context.subscribe("interval.tick", function () {
            if (sent || ++ticks % 5 !== 0 || !rtsBridge || attempts >= 30) return;
            var snapshot = rtsBridge.getActors();
            if (!snapshot.session) return;
            var marines = snapshot.units.filter(function (unit) {
                return unit.kind === "terran_marine" && unit.hp > 0;
            });
            if (!marines.length) return;
            attempts++;
            context.executeAction("rtsbridge.marineCommand", {
                session: snapshot.session, request: 7000 + attempts,
                unit_ids: marines.map(function (unit) { return unit.id; }),
                verb: "attack", target_entity_id: "openrct2:ride:1#1"
            }, function (result) {
                sent = !result.error;
                console.log("WORLD_TARGET_ATTACK_QUERY accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
            });
        });
    }
});
