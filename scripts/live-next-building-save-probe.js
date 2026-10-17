/* Test-only host save after a new supported building is constructed. */
registerPlugin({ name: "Next building save probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "server") return;
    let builtAt = 0, saved = false;
    context.subscribe("action.execute", function (event) {
        if (event.action === "largesceneryplace" && event.args && !event.result.error) {
            builtAt = Date.now();
            console.log("NEXT_BUILDING_SAVE_BUILT x=" + event.args.x + " y=" + event.args.y);
        }
    });
    context.subscribe("interval.tick", function () {
        if (!saved && builtAt && Date.now() - builtAt >= 15000) {
            saved = true;
            context.saveGame({ filename: "next-building-recovery" });
            console.log("NEXT_BUILDING_SAVE_SAVED");
        }
    });
}});
