/* Test-only host save after a client constructs the Mt. Zergling Barracks. */
registerPlugin({ name: "Barracks save probe", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        if (network.mode !== "server") return;
        let builtAt = 0, saved = false;
        context.subscribe("action.execute", function (event) {
            if (event.action === "largesceneryplace" && event.args
                && event.args.x === 3200 && event.args.y === 3328 && !event.result.error) {
                builtAt = Date.now();
                console.log("BARRACKS_SAVE_PROBE_BUILT");
            }
        });
        context.subscribe("interval.tick", function () {
            if (!saved && builtAt && Date.now() - builtAt >= 15000) {
                saved = true;
                context.saveGame({ filename: "barracks-recovery" });
                console.log("BARRACKS_SAVE_PROBE_SAVED");
            }
        });
    }
});
