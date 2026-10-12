/* Local integration fixture: command Marines to attack the playable park carousel. */
registerPlugin({ name: "World Bridge Target Probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "client") return;
        var ticks = 0, sent = false, attempts = 0, observed = false;
        context.subscribe("interval.tick", function () {
            if (sent || ++ticks % 20 !== 0 || !rtsBridge || attempts >= 100) return;
            var snapshot = rtsBridge.getActors();
            if (!snapshot.session) return;
            var marines = snapshot.units.filter(function (unit) {
                return unit.kind === "terran_marine" && unit.hp > 0;
            });
            if (!observed) {
                observed = true;
                console.log("WORLD_TARGET_PROBE actors=" + snapshot.units.length
                    + " marines=" + marines.length + " session=" + snapshot.session);
            }
            if (!marines.length) return;
            attempts++;
            if (attempts === 1 || attempts % 10 === 0)
                console.log("WORLD_TARGET_ATTACK_REQUEST attempt=" + attempts);
            context.executeAction("rtsbridge.marineCommand", {
                session: snapshot.session, request: 7000 + attempts,
                unit_ids: marines.map(function (unit) { return unit.id; }),
                verb: "attack", target_entity_id: "openrct2:ride:0#1"
            }, function (result) {
                sent = !result.error;
                console.log("WORLD_TARGET_ATTACK_QUERY accepted=" + !result.error
                    + " reason=" + (result.errorMessage || "ok"));
            });
        });
    }
});
