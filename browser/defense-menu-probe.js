/* Test-only browser probe for the two StarCraft windows. */
registerPlugin({ name: "StarCoaster defense menu probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    var constructionSeen = false, defenseSeen = false;
    context.subscribe("interval.tick", function () {
        if (network.mode !== "client") return;
        var construction = ui.getWindow("starcoaster-construction");
        if (construction && !constructionSeen) {
            constructionSeen = true;
            console.log("DEFENSE_CONSTRUCTION_WINDOW x=" + construction.x + " y=" + construction.y
                + " width=" + construction.width + " height=" + construction.height);
        }
        var defense = ui.getWindow("starcoaster-defense");
        if (defense && !defenseSeen) {
            defenseSeen = true;
            console.log("DEFENSE_WINDOW x=" + defense.x + " y=" + defense.y
                + " width=" + defense.width + " height=" + defense.height);
        }
    });
} });
