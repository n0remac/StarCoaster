// Test-only: let joined clients exercise normal construction game actions.
registerPlugin({ name: "Live Construction Permissions", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "server") return;
        context.subscribe("network.join", function (event) {
            context.executeAction("playersetgroup", { playerId: event.player, groupId: 0 },
                function (result) {
                    console.log("LIVE_CONSTRUCTION_GROUP player=" + event.player
                        + " accepted=" + !result.error + " reason=" + (result.errorMessage || "ok"));
                });
        });
    }
});
