/* Local integration fixture: command a Marine to attack an existing park ride. */
registerPlugin({ name: "World Bridge Target Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        var ticks = 0, sent = false;
        context.subscribe("interval.tick", function () {
            if (sent || ++ticks % 20 !== 0 || !rtsBridge) return;
            var snapshot = rtsBridge.getActors();
            if (!snapshot.session) return;
            var marine = snapshot.units.filter(function (unit) {
                return unit.kind === "terran_marine" && unit.hp > 0;
            })[0];
            if (!marine) return;
            sent = true;
            context.executeAction("rtsbridge.marineCommand", {
                session: snapshot.session, request: 7001, unit_ids: [marine.id],
                verb: "attack", target_entity_id: "openrct2:ride:1#1"
            }, function (result) {
                console.log("WORLD_TARGET_ATTACK_QUERY accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
            });
        });
    }
});
