/* Test-only multiplayer probe: the second client must not change defense. */
registerPlugin({ name: "Universal Defense Noncommander Probe", version: "1.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
        var ticks = 0, pending = false, finished = false;
        context.subscribe("interval.tick", function () {
            if (network.mode !== "client" || finished || pending || ++ticks % 24 !== 0) return;
            if (!rtsBridge) {
                if (ticks % 240 === 0) console.log("UNAUTHORIZED_WAIT bridge_unavailable");
                return;
            }
            var actors = rtsBridge.getActors();
            if (!actors || !actors.session) {
                if (ticks % 240 === 0) console.log("UNAUTHORIZED_WAIT session_unavailable");
                return;
            }
            pending = true;
            console.log("UNAUTHORIZED_ATTEMPT player=" + network.currentPlayer.id);
            context.executeAction("rtsbridge.configureDefense",
                { session: actors.session, enabled: false }, function (result) {
                    pending = false;
                    console.log("UNAUTHORIZED_RESPONSE accepted=" + !result.error
                        + " reason=" + (result.errorMessage || "ok"));
                    if (!result.error || /commander/i.test(result.errorMessage || "")) {
                        finished = true;
                        console.log("UNAUTHORIZED_DEFENSE local_accepted=" + !result.error
                            + " reason=" + (result.errorMessage || "ok"));
                    }
                });
        });
    }
});
