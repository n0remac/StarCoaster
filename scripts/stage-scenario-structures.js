/* Scenario-specific values are injected by stage-scenario-structures.py. */
var starcoasterStructures = __STARCOASTER_STRUCTURES__;
registerPlugin({ name: "Passthrough RTS Bridge", version: "0.3.0",
    authors: ["Passthrough RTS project"], type: "remote", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
        if (network.mode !== "server") return;
        var done = false;
        function fail(reason) { done = true; console.log("SCENARIO_STRUCTURES_FAILED " + reason); }
        context.subscribe("interval.tick", function () {
            if (done) return;
            done = true;
            try {
                var occupied = {}, placements = [];
                starcoasterStructures.forEach(function (spec) {
                    var object = objectManager.getAllObjects("large_scenery").find(function (item) {
                        return item.identifier === spec.object_id;
                    });
                    if (!object) {
                        objectManager.load(spec.object_id);
                        object = objectManager.getAllObjects("large_scenery").find(function (item) {
                            return item.identifier === spec.object_id;
                        });
                    }
                    if (!object) throw new Error(spec.id + ": object unavailable " + spec.object_id);
                    var height = null;
                    for (var y = spec.tile[1]; y < spec.tile[1] + spec.height; y++) {
                        for (var x = spec.tile[0]; x < spec.tile[0] + spec.width; x++) {
                            if (x < 8 || y < 8 || x >= map.size.x - 8 || y >= map.size.y - 8)
                                throw new Error(spec.id + ": footprint outside buildable map");
                            var key = x + ":" + y, tile = map.getTile(x, y);
                            if (occupied[key]) throw new Error(spec.id + ": overlapping structure at " + key);
                            occupied[key] = true;
                            var surface = null;
                            for (var i = 0; i < tile.numElements; i++) {
                                var element = tile.getElement(i);
                                if (element.type === "surface") surface = element;
                                else throw new Error(spec.id + ": obstructed by " + element.type + " at " + key);
                            }
                            if (!surface || surface.slope || surface.waterHeight)
                                throw new Error(spec.id + ": unsuitable terrain at " + key);
                            if (height === null) height = surface.baseHeight;
                            if (height !== surface.baseHeight)
                                throw new Error(spec.id + ": uneven terrain at " + key);
                        }
                    }
                    placements.push({ spec: spec, object: object, height: height });
                });
                var ownership = [];
                placements.forEach(function (entry) {
                    var spec = entry.spec, sequence = 0;
                    for (var y = spec.tile[1]; y < spec.tile[1] + spec.height; y++) {
                        for (var x = spec.tile[0]; x < spec.tile[0] + spec.width; x++) {
                            var tile = map.getTile(x, y);
                            // Native combat removal uses the ordinary scenery action.
                            // Give only the occupied cells park ownership in the derived save.
                            for (var i = 0; i < tile.numElements; i++) {
                                var surface = tile.getElement(i);
                                if (surface.type === "surface") surface.ownership = 2;
                            }
                            tile.insertElement(tile.numElements);
                            var element = tile.getElement(tile.numElements - 1);
                            element.type = "large_scenery";
                            element.object = entry.object.index;
                            element.baseHeight = entry.height;
                            element.clearanceHeight = entry.height + 6;
                            element.direction = 0;
                            element.sequence = sequence++;
                            element.primaryColour = 0;
                            element.secondaryColour = 0;
                            element.tertiaryColour = 0;
                        }
                    }
                    ownership.push({ id: spec.id, type: spec.type, x: spec.tile[0], y: spec.tile[1],
                        z: entry.height * 8, owner: spec.owner });
                });
                context.getParkStorage().set("scenarioStructures", ownership);
                context.saveGame({ filename: "scenario-structures" });
                console.log("SCENARIO_STRUCTURES_STAGED " + JSON.stringify(ownership));
            } catch (error) { fail(String(error)); }
        });
    }
});
