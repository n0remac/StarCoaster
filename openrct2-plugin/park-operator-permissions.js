// Give the first joined player the OpenRCT2 administrator group so normal
// multiplayer construction and park management are available during play.
registerPlugin({ name: "StarCoaster Park Operator", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "server") return;
        let operator = -1;
        function joinedPlayers(exclude) {
            const server = network.currentPlayer.id;
            return network.players.filter(function (player) {
                return player.id !== server && player.id !== exclude;
            }).map(function (player) { return player.id; });
        }
        function grant(player) {
            if (player === operator) return;
            operator = player;
            if (player < 0) return;
            context.executeAction("playersetgroup", { playerId: player, groupId: 0 },
                function (result) {
                    console.log("PARK_OPERATOR_GROUP player=" + player
                        + " accepted=" + !result.error + " reason=" + (result.errorMessage || "ok"));
                });
        }
        context.subscribe("network.join", function (event) {
            const joined = joinedPlayers(-1);
            if (!joined.includes(event.player)) joined.push(event.player);
            grant(Math.min.apply(null, joined));
        });
        context.subscribe("network.leave", function (event) {
            if (event.player !== operator) return;
            const joined = joinedPlayers(event.player);
            grant(joined.length ? Math.min.apply(null, joined) : -1);
        });
    }
});
