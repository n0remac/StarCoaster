/* One-time, local park generator loaded by scripts/create-render-test-park.py. */
registerPlugin({
    name: "RTS Bridge Render Test Park Generator",
    version: "1.0.0",
    authors: ["StarCoaster"],
    type: "local",
    licence: "MIT",
    targetApiVersion: 124,
    minApiVersion: 124,
    main: function () {
        var done = false;
        context.subscribe("interval.tick", function () {
            if (done || network.mode !== "server") return;
            done = true;
            function add(x, y, type, base, clearance, object) {
                var tile = map.getTile(x, y);
                tile.insertElement(tile.numElements);
                var element = tile.getElement(tile.numElements - 1);
                element.type = type;
                element.baseHeight = base;
                element.clearanceHeight = clearance;
                element.object = object;
                return element;
            }
            // The OpenBW actor traverses y=480, x=320..640 (tiles 10..20,15).
            // Add a visible path, trees on both sides, a fence in front, and
            // a raised section along the last part of the route.
            for (var x = 18; x <= 21; x++) {
                for (var y = 14; y <= 16; y++) {
                    var surface = map.getTile(x, y).getElement(0);
                    surface.baseHeight = 16;
                    surface.clearanceHeight = 16;
                }
            }
            for (var px = 10; px <= 20; px++) {
                var height = px >= 18 ? 16 : 14;
                var path = add(px, 15, "footpath", height, height + 2, 4);
                path.surfaceObject = 4;
                path.railingsObject = 0;
                path.edges = 5;
            }
            var treeNorth = add(13, 14, "small_scenery", 14, 26, 31);
            treeNorth.quadrant = 0;
            var treeSouth = add(14, 16, "small_scenery", 14, 26, 31);
            treeSouth.quadrant = 0;
            var treeEnd = add(19, 16, "small_scenery", 16, 28, 98);
            treeEnd.quadrant = 0;
            for (var wx = 16; wx <= 17; wx++) {
                var wall = add(wx, 16, "wall", 14, 18, 9);
                wall.direction = 0;
            }
            context.saveGame({ filename: "bridge-render-test" });
            console.log("RTS render test park saved");
        });
    }
});
