/* Deterministic Frontier Outpost fixture. Run only on the headless generator. */
registerPlugin({
    name: "Frontier Outpost Generator", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        var started = false;
        var savePending = false;
        var probe = false; // The Python launcher substitutes this literal for an isolated probe.
        var bounds = { min_x: 8, min_y: 8, max_x: 55, max_y: 55 };
        var specs = [
            { id: "carousel-1", name: "Frontier Carousel", object: "rct2.ride.mgr1", x: 19, y: 18, track: 266, expected: 9,
                proxy_type: "Terran_Barracks", proxy_unit_type: 111, proxy_hp: 1000, collision: { width: 105, height: 73 } },
            { id: "shop-1", name: "Frontier Burger Bar", object: "rct2.ride.burgb", x: 39, y: 19, track: 262, expected: 1,
                proxy_type: "Terran_Missile_Turret", proxy_unit_type: 124, proxy_hp: 200, collision: { width: 33, height: 49 } },
            { id: "ride-2", name: "Frontier Ferris Wheel", object: "rct2.ride.fwh1", x: 42, y: 39, track: 265, expected: 4,
                proxy_type: "Terran_Armory", proxy_unit_type: 123, proxy_hp: 750, collision: { width: 96, height: 55 } }
        ];
        function fail(message) { console.log("PARK_ASSAULT_FAILED " + message); }
        function object(type, identifier) {
            var matches = objectManager.getAllObjects(type).filter(function (entry) {
                return entry.identifier === identifier;
            });
            if (matches.length !== 1) throw new Error("object unavailable: " + type + " " + identifier);
            return matches[0];
        }
        function add(x, y, type, base, clearance, index) {
            var tile = map.getTile(x, y);
            tile.insertElement(tile.numElements);
            var element = tile.getElement(tile.numElements - 1);
            element.type = type;
            element.baseHeight = base;
            element.clearanceHeight = clearance;
            element.object = index;
            return element;
        }
        function footprint(rideId) {
            var cells = [];
            for (var x = bounds.min_x; x <= bounds.max_x; x++) {
                for (var y = bounds.min_y; y <= bounds.max_y; y++) {
                    var tile = map.getTile(x, y);
                    for (var i = 0; i < tile.numElements; i++) {
                        var e = tile.getElement(i);
                        if (e.type === "track" && e.ride === rideId)
                            cells.push({ x: x, y: y, z: e.baseHeight * 8, track_type: e.trackType, sequence: e.sequence });
                    }
                }
            }
            return cells;
        }
        function structureCenter(tiles) {
            // The centre of occupied track tile area also handles a one-tile shop
            // and an even-width, asymmetric ride without depending on placement origin.
            var unique = {};
            tiles.forEach(function (tile) { unique[tile.x + "," + tile.y] = tile; });
            var occupied = Object.keys(unique).map(function (key) { return unique[key]; });
            var x = 0, y = 0;
            occupied.forEach(function (tile) { x += tile.x * 32 + 16; y += tile.y * 32 + 16; });
            return { x: Math.round(x / occupied.length), y: Math.round(y / occupied.length) };
        }
        function scenery() {
            var paths = {};
            function path(x, y) { paths[x + "," + y] = true; }
            // Perimeter loop with spokes and two intersections. All tiles are real paths.
            for (var x = 14; x <= 50; x++) { path(x, 14); path(x, 50); path(x, 31); }
            for (var y = 14; y <= 50; y++) { path(14, y); path(50, y); path(32, y); }
            for (var x2 = 17; x2 <= 46; x2++) { path(x2, 24); path(x2, 43); }
            for (var y2 = 17; y2 <= 46; y2++) { path(24, y2); path(44, y2); }
            Object.keys(paths).forEach(function (key) {
                var point = key.split(",").map(Number);
                var e = add(point[0], point[1], "footpath", 14, 16, 4);
                e.surfaceObject = 4; e.railingsObject = 0; e.edges = 15;
            });
            var fence = object("wall", "rct2.scenery_wall.wpf").index;
            var solid = object("wall", "rct2.scenery_wall.wbr1").index;
            function wall(x, y, direction, index) {
                var e = add(x, y, "wall", 14, 18, index);
                e.direction = direction;
            }
            // Edged perimeter with two clear entrances on the west and south.
            for (var px = 12; px <= 53; px++) {
                if (px < 29 || px > 39) wall(px, 12, 0, fence);
                if (px < 33 || px > 36) wall(px, 53, 0, fence);
            }
            for (var py = 12; py <= 53; py++) {
                if (py < 19 || py > 24) wall(12, py, 1, fence);
                wall(53, py, 1, fence);
            }
            // Long direct barrier, offset return, and a one tile chokepoint.
            for (var wy = 16; wy <= 39; wy++) if (wy < 34 || wy > 36) wall(28, wy, 1, solid);
            for (var wx = 29; wx <= 43; wx++) if (wx < 31 || wx > 33) wall(wx, 35, 0, solid);
            for (var bx = 29; bx <= 44; bx++) if (bx < 34 || bx > 40) wall(bx, 17, 0, solid);
            for (var mx = 17; mx <= 26; mx++) if (mx < 22 || mx > 24) wall(mx, 38, 0, fence);
            for (var my = 38; my <= 46; my++) if (my < 40 || my > 42) wall(21, my, 1, fence);
            var plants = [
                [16, 16, "tap"], [17, 28, "tbr"], [18, 45, "tcf"], [20, 27, "tg1"],
                [22, 16, "tf1"], [25, 27, "tg2"], [26, 46, "tco"], [29, 19, "tbr"],
                [30, 47, "tf2"], [34, 18, "tap"], [35, 27, "tg3"], [49, 46, "tcf"],
                [38, 28, "tf1"], [48, 47, "tbr"], [46, 18, "tco"], [47, 27, "tg4"],
                [48, 40, "tf2"], [18, 34, "tg5"], [35, 39, "tf1"], [45, 45, "tg3"]
            ];
            plants.forEach(function (p) {
                var e = add(p[0], p[1], "small_scenery", 14, 26,
                    object("small_scenery", "rct2.scenery_small." + p[2]).index);
                e.quadrant = 0;
            });
        }
        function metadata() {
            var targets = specs.map(function (spec) {
                var rides = map.rides.filter(function (ride) { return ride.name === spec.name; });
                if (rides.length !== 1) throw new Error("missing named ride " + spec.name);
                var ride = rides[0];
                var tiles = footprint(ride.id);
                if (ride.status !== "closed" || !ride.isEmpty || ride.object.identifier !== spec.object
                    || tiles.length !== spec.expected || tiles.some(function (tile) { return tile.z !== 112; }))
                    throw new Error("invalid constructed ride " + spec.id + " " + JSON.stringify({ ride: ride.id, tiles: tiles }));
                var center = structureCenter(tiles);
                return { id: spec.id, ride_id: ride.id, ride_type: ride.type,
                    object_id: ride.object.identifier, name: ride.name, status: ride.status,
                    empty: ride.isEmpty, structure_center: center, proxy_world: center,
                    proxy_type: spec.proxy_type, proxy_unit_type: spec.proxy_unit_type,
                    proxy_hp: spec.proxy_hp, proxy_collision: spec.collision,
                    attack_approaches: [], footprint_tiles: tiles.map(function (tile) { return { x: tile.x, y: tile.y }; }),
                    tiles: tiles };
            });
            return { name: "Frontier Outpost", bounds: bounds, tile_size: 32,
                cell_size: 8, transform: { x: -128, y: -96 }, targets: targets };
        }
        function navigationElements() {
            var wallObjects = objectManager.getAllObjects("wall");
            var smallObjects = objectManager.getAllObjects("small_scenery");
            var rows = [], elements = [];
            for (var y = bounds.min_y; y <= bounds.max_y; y++) {
                var heights = [];
                for (var x = bounds.min_x; x <= bounds.max_x; x++) {
                    var tile = map.getTile(x, y), surface = null;
                    for (var i = 0; i < tile.numElements; i++) {
                        var e = tile.getElement(i);
                        if (e.type === "surface") { surface = e; continue; }
                        if (e.type !== "footpath" && e.type !== "wall"
                            && e.type !== "small_scenery" && e.type !== "track") continue;
                        var record = { x: x, y: y, type: e.type, z: e.baseHeight * 8 };
                        if (e.type === "track") { record.ride_id = e.ride; record.track_type = e.trackType; }
                        if (e.type === "wall") {
                            record.direction = e.direction;
                            record.object_id = wallObjects.filter(function (o) { return o.index === e.object; })[0].identifier;
                        }
                        if (e.type === "small_scenery") {
                            record.quadrant = e.quadrant;
                            record.object_id = smallObjects.filter(function (o) { return o.index === e.object; })[0].identifier;
                        }
                        if (e.type === "footpath") record.edges = e.edges;
                        elements.push(record);
                    }
                    if (!surface) throw new Error("surface missing at " + x + "," + y);
                    heights.push(surface.baseHeight * 8);
                }
                rows.push(heights);
            }
            return { bounds: bounds, tile_size: 32, cell_size: 8, elevation_rows: rows, elements: elements };
        }
        function createAt(index) {
            if (index === specs.length) {
                try {
                    console.log("PARK_ASSAULT_NAV " + JSON.stringify(navigationElements()));
                    console.log("PARK_ASSAULT_METADATA " + JSON.stringify(metadata()));
                    savePending = true;
                }
                catch (error) { fail(String(error)); }
                return;
            }
            var spec = specs[index];
            var entry;
            try { entry = object("ride", spec.object); } catch (error) { fail(String(error)); return; }
            var rideType = entry.rideType[0];
            context.executeAction("ridecreate", { rideType: rideType, rideObject: entry.index,
                entranceObject: 0, colour1: 0, colour2: 0, inspectionInterval: 0 }, function (created) {
                if (created.error || !Number.isInteger(created.ride)) { fail("ridecreate " + spec.id + " " + JSON.stringify(created)); return; }
                var rideId = created.ride;
                context.executeAction("trackplace", { x: spec.x * 32, y: spec.y * 32, z: 112,
                    direction: 0, ride: rideId, trackType: spec.track, rideType: rideType,
                    brakeSpeed: 0, colour: 0, seatRotation: 0, trackPlaceFlags: 0,
                    isFromTrackDesign: false }, function (placed) {
                    if (placed.error) { fail("trackplace " + spec.id + " " + JSON.stringify(placed)); return; }
                    context.executeAction("ridesetname", { ride: rideId, name: spec.name }, function (named) {
                        if (named.error) { fail("ridesetname " + spec.id + " " + JSON.stringify(named)); return; }
                        createAt(index + 1);
                    });
                });
            });
        }
        function probeNext(index, results) {
            if (index === specs.length) { console.log("PARK_ASSAULT_PROBE " + JSON.stringify(results)); return; }
            var spec = specs[index];
            var matches = map.rides.filter(function (ride) { return ride.name === spec.name; });
            if (matches.length !== 1) { fail("probe identity " + spec.id); return; }
            var ride = matches[0], before = footprint(ride.id);
            context.executeAction("ridedemolish", { ride: ride.id, modifyType: 0 }, function (result) {
                var after = footprint(ride.id);
                results.push({ id: spec.id, ride_id: ride.id, error: result.error || 0,
                    before: before.length, after: after.length, removed: !map.getRide(ride.id) && after.length === 0 });
                probeNext(index + 1, results);
            });
        }
        context.subscribe("interval.tick", function () {
            if (network.mode !== "server") return;
            if (savePending) { savePending = false; context.saveGame({ filename: "frontier-outpost" }); return; }
            if (started) return;
            started = true;
            if (probe) { try { metadata(); probeNext(0, []); } catch (error) { fail(String(error)); } return; }
            try { park.name = "Frontier Outpost"; scenery(); createAt(0); }
            catch (error) { fail(String(error)); }
        });
    }
});
