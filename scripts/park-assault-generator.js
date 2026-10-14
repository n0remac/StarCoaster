/* Deterministic Frontier Outpost fixture. Run only on the headless generator. */
registerPlugin({
    name: "Frontier Outpost Generator", version: "1.0.0", authors: ["StarCoaster"],
    type: "local", licence: "MIT", targetApiVersion: 124, minApiVersion: 124,
    main: function () {
        var started = false;
        var savePending = false;
        var resizePending = false;
        var preparation = false;
        var sourceRides = [];
        var cleanupBusy = false;
        var sourcePeopleCleared = false;
        var resizeRequested = false;
        var probe = false; // The Python launcher substitutes this literal for an isolated probe.
        var playable = false; // The playable launcher substitutes this literal.
        var bounds = { min_x: 8, min_y: 8, max_x: 55, max_y: 55 };
        var specs = [
            { id: "carousel-1", name: "Frontier Carousel", object: "rct2.ride.mgr1", x: 19, y: 18, track: 266, expected: 9,
                proxy_type: "Terran_Barracks", proxy_unit_type: 111, proxy_hp: 1000, collision: { width: 105, height: 73 } },
            { id: "shop-1", name: "Frontier Burger Bar", object: "rct2.ride.burgb", x: 39, y: 19, track: 262, expected: 1,
                proxy_type: "Terran_Missile_Turret", proxy_unit_type: 124, proxy_hp: 200, collision: { width: 33, height: 49 } },
            { id: "ride-2", name: "Frontier Ferris Wheel", object: "rct2.ride.fwh1", x: 42, y: 39, track: 265, expected: 4,
                proxy_type: "Terran_Armory", proxy_unit_type: 123, proxy_hp: 750, collision: { width: 96, height: 55 } }
        ];
        if (playable) specs.push({ id: "shop-2", name: "Frontier Drink Stand", object: "rct2.ride.drnks", x: 42, y: 22,
            track: 262, expected: 1, proxy_type: "Terran_Missile_Turret", proxy_unit_type: 124,
            proxy_hp: 200, collision: { width: 33, height: 49 } });
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
        function ridgeSurface(x, y) {
            if (!playable) return { base: 14, slope: 0 };
            if (x >= 14 && x <= 24 && y >= 30 && y <= 34) return { base: 16, slope: 0 };
            if (x >= 14 && x <= 18 && y === 29) return { base: 14, slope: 6 };
            if (x >= 14 && x <= 18 && y === 35) return { base: 14, slope: 9 };
            if (x === 25 && y >= 30 && y <= 34) return { base: 14, slope: 3 };
            return { base: 14, slope: 0 };
        }
        function terrain() {
            for (var y = bounds.min_y; y <= bounds.max_y; y++) {
                for (var x = bounds.min_x; x <= bounds.max_x; x++) {
                    var expected = ridgeSurface(x, y);
                    if (expected.base === 14 && expected.slope === 0) continue;
                    var tile = map.getTile(x, y), surface = null;
                    for (var i = 0; i < tile.numElements; i++)
                        if (tile.getElement(i).type === "surface") surface = tile.getElement(i);
                    if (!surface) throw new Error("missing terrain at " + x + "," + y);
                    surface.baseHeight = expected.base;
                    surface.clearanceHeight = expected.base;
                    surface.slope = expected.slope;
                }
            }
        }
        function scenery() {
            var paths = {};
            function path(x, y) { paths[x + "," + y] = true; }
            function horizontal(y, x0, x1) {
                for (var x = x0; x <= x1; x++) path(x, y);
            }
            function vertical(x, y0, y1) {
                for (var y = y0; y <= y1; y++) path(x, y);
            }
            function plaza(x0, y0, x1, y1) {
                for (var y = y0; y <= y1; y++) horizontal(y, x0, x1);
            }
            // Three connected districts branch from a bent central promenade.
            // Keep the carousel's 3x3 track footprint clear inside its plaza.
            horizontal(22, 15, 31);
            vertical(17, 16, 22); vertical(23, 16, 22);
            horizontal(16, 17, 23);
            horizontal(21, 18, 22);
            for (var cy = 18; cy <= 20; cy++) { path(17, cy); path(23, cy); }
            vertical(15, 22, 31); horizontal(31, 15, 26);
            plaza(14, 28, 18, 29); horizontal(34, 14, 25);
            vertical(14, 29, 34); vertical(25, 31, 34);
            vertical(31, 22, 42); horizontal(42, 31, 39);
            horizontal(26, 31, 45); vertical(45, 26, 36);
            // Food court: two shop fronts share a small paved square.
            plaza(36, 23, 44, 25); vertical(36, 18, 23);
            horizontal(18, 36, 45); vertical(45, 18, 25);
            horizontal(21, 36, 40); horizontal(21, 43, 45);
            // Ferris wheel garden and the south entrance join the promenade.
            horizontal(36, 39, 49); vertical(39, 36, 44);
            horizontal(44, 39, 49); vertical(49, 36, 44);
            horizontal(42, 31, 39); vertical(34, 42, 50);
            horizontal(50, 34, 36); vertical(36, 44, 50);
            // Meandering outer walk offers a second route around each district.
            horizontal(14, 15, 28); vertical(28, 14, 22);
            horizontal(14, 28, 48); vertical(48, 14, 18);
            horizontal(18, 45, 48); vertical(49, 18, 36);
            horizontal(46, 15, 34); vertical(15, 34, 46);
            horizontal(46, 34, 49);
            Object.keys(paths).forEach(function (key) {
                var point = key.split(",").map(Number);
                var ground = ridgeSurface(point[0], point[1]);
                var e = add(point[0], point[1], "footpath", ground.base, ground.base + 2, 4);
                e.surfaceObject = 4; e.railingsObject = 0; e.edges = 15;
                if (ground.slope) e.slopeDirection = { 6: 1, 9: 3, 3: 0 }[ground.slope];
            });
            if (playable && !objectManager.getAllObjects("wall").some(function (entry) {
                return entry.identifier === "rct2.scenery_wall.wbr2";
            }) && !objectManager.load("rct2.scenery_wall.wbr2"))
                throw new Error("destructible wall object unavailable");
            var fence = object("wall", "rct2.scenery_wall.wpf").index;
            var solid = object("wall", "rct2.scenery_wall.wbr1").index;
            var gate = playable ? object("wall", "rct2.scenery_wall.wbr2").index : solid;
            var wallTiles = {};
            function wall(x, y, direction, index) {
                var e = add(x, y, "wall", 14, 18, index);
                e.direction = direction;
                wallTiles[x + "," + y] = true;
            }
            // Native edge directions: 0 west, 1 south, 2 east, 3 north.
            // Segments on adjacent tiles share an endpoint in world space.
            for (var px = 12; px <= 53; px++) {
                if (px < 29 || px > 39) wall(px, 12, 3, fence);
                if (px < 33 || px > 36) wall(px, 53, 1, fence);
            }
            for (var py = 12; py <= 53; py++) {
                if (py < 19 || py > 24) wall(12, py, 0, fence);
                wall(53, py, 2, fence);
            }
            // Defense barrier retains the destructible tile and the long
            // blocked corridor used by the native navigation regression.
            for (var wy = 16; wy <= 39; wy++) if (playable ? wy !== 35 : (wy < 34 || wy > 36)) wall(28, wy, 0, solid);
            if (playable) wall(28, 35, 0, gate);
            for (var wx = 28; wx <= 43; wx++) if (wx < 31 || wx > 33) wall(wx, 35, 3, solid);
            // Continuous food court rear boundary with a deliberate shop gap.
            for (var bx = 35; bx <= 46; bx++) if (bx < 40 || bx > 42) wall(bx, 16, 3, solid);
            wall(35, 16, 0, solid); wall(46, 16, 2, solid);
            // Low fence around the Marine staging garden; east side is open.
            for (var mx = 14; mx <= 25; mx++) if (mx < 19 || mx > 21) wall(mx, 36, 1, fence);
            for (var my = 27; my <= 35; my++) wall(13, my, 0, fence);
            for (var my2 = 27; my2 <= 29; my2++) wall(25, my2, 2, fence);
            var plants = [
                [16, 16, "tap"], [17, 28, "tbr"], [18, 45, "tcf"], [20, 27, "tg1"],
                [22, 16, "tf1"], [25, 27, "tg2"], [26, 46, "tco"], [29, 19, "tbr"],
                [30, 47, "tf2"], [34, 18, "tap"], [35, 27, "tg3"], [49, 46, "tcf"],
                [38, 28, "tf1"], [48, 47, "tbr"], [46, 18, "tco"], [47, 27, "tg4"],
                [48, 40, "tf2"], [18, 34, "tg5"], [35, 39, "tf1"], [45, 45, "tg3"],
                [10, 16, "tap"], [10, 25, "tco"], [10, 35, "tbr"], [10, 46, "tcf"],
                [54, 16, "tap"], [54, 25, "tco"], [54, 35, "tbr"], [54, 46, "tcf"],
                [16, 18, "tf1"], [16, 20, "tg2"], [24, 18, "tg3"], [24, 20, "tf2"],
                [18, 23, "tg4"], [20, 23, "tg1"], [22, 23, "tg5"],
                [35, 19, "tco"], [37, 20, "tg1"], [40, 20, "tf1"],
                [41, 24, "tg3"], [43, 24, "tf2"], [46, 24, "tbr"],
                [18, 27, "tf1"], [20, 28, "tg4"], [22, 28, "tg2"],
                [18, 35, "tf2"], [20, 35, "tg1"], [22, 35, "tg5"],
                [38, 38, "tg4"], [39, 40, "tf1"], [44, 41, "tg2"],
                [46, 38, "tf2"], [47, 42, "tg3"], [38, 46, "tco"],
                [26, 44, "tap"], [29, 45, "tg5"], [31, 47, "tbr"]
            ];
            plants.forEach(function (p) {
                if (paths[p[0] + "," + p[1]] || wallTiles[p[0] + "," + p[1]]) return;
                var ground = ridgeSurface(p[0], p[1]);
                if (ground.slope) return;
                var e = add(p[0], p[1], "small_scenery", ground.base, ground.base + 12,
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
            return { name: "Frontier Outpost", layout_version: playable ? 4 : 1,
                bounds: bounds, tile_size: 32,
                cell_size: 8, transform: playable ? { x: 1024, y: 1024 } : { x: -128, y: -96 }, targets: targets };
        }
        function navigationElements() {
            var wallObjects = objectManager.getAllObjects("wall");
            var smallObjects = objectManager.getAllObjects("small_scenery");
            var rows = [], slopes = [], water = [], elements = [];
            for (var y = bounds.min_y; y <= bounds.max_y; y++) {
                var heights = [], rowSlopes = [], rowWater = [];
                for (var x = bounds.min_x; x <= bounds.max_x; x++) {
                    var tile = map.getTile(x, y), surface = null;
                    for (var i = 0; i < tile.numElements; i++) {
                        var e = tile.getElement(i);
                        if (e.type === "surface") { surface = e; continue; }
                        if (e.type !== "footpath" && e.type !== "wall"
                            && e.type !== "small_scenery" && e.type !== "large_scenery" && e.type !== "track") continue;
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
                        if (e.type === "large_scenery") {
                            record.sequence = e.sequence; record.direction = e.direction;
                            record.object_id = objectManager.getAllObjects("large_scenery")
                                .filter(function (o) { return o.index === e.object; })[0].identifier;
                        }
                        if (e.type === "footpath") {
                            record.edges = e.edges;
                            record.slope_direction = Number.isInteger(e.slopeDirection) ? e.slopeDirection : null;
                        }
                        elements.push(record);
                    }
                    if (!surface) throw new Error("surface missing at " + x + "," + y);
                    heights.push(surface.baseHeight * 8);
                    rowSlopes.push(surface.slope || 0);
                    rowWater.push(surface.waterHeight || 0);
                }
                rows.push(heights);
                slopes.push(rowSlopes);
                water.push(rowWater);
            }
            return { bounds: bounds, tile_size: 32, cell_size: 8,
                elevation_rows: rows, slope_rows: slopes, water_rows: water, elements: elements };
        }
        function createAt(index) {
            if (index === specs.length) {
                placeLarge(0);
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
        function placeLarge(index) {
            var placements = playable ? [[17, 38, "rct2.scenery_large.sip"],
                [9, 29, "rct2.scenery_large.ssig4"]] : [];
            if (index === placements.length) {
                try {
                    console.log("PARK_ASSAULT_NAV " + JSON.stringify(navigationElements()));
                    console.log("PARK_ASSAULT_METADATA " + JSON.stringify(metadata()));
                    savePending = true;
                } catch (error) { fail(String(error)); }
                return;
            }
            var placement = placements[index], entry;
            try { entry = object("large_scenery", placement[2]); }
            catch (error) { fail(String(error)); return; }
            context.executeAction("largesceneryplace", { x: placement[0] * 32, y: placement[1] * 32,
                z: 112, direction: 0, object: entry.index, primaryColour: 0,
                secondaryColour: 0, tertiaryColour: 0 }, function (result) {
                if (result.error) fail("largesceneryplace " + placement[2] + " " + JSON.stringify(result));
                else placeLarge(index + 1);
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
            if (savePending) { savePending = false; context.saveGame({ filename: playable ? "frontier-outpost-playable" : "frontier-outpost" }); return; }
            if (resizePending) { resizePending = false; populate(); return; }
            if (preparation) {
                if (cleanupBusy) return;
                if (sourceRides.length) {
                    const rideId = sourceRides.shift();
                    cleanupBusy = true;
                    context.executeAction("ridedemolish", { ride: rideId, modifyType: 0 }, function (result) {
                        if (result.error) fail("source ride demolition " + rideId + " " + JSON.stringify(result));
                        cleanupBusy = false;
                    });
                    return;
                }
                if (!sourcePeopleCleared) {
                    ["guest", "staff", "car"].forEach(function (kind) {
                        map.getAllEntities(kind).forEach(function (entity) { entity.remove(); });
                    });
                    sourcePeopleCleared = true;
                    return;
                }
                if (!resizeRequested) {
                    resizeRequested = true;
                    context.executeAction("mapchangesize", { targetSizeX: 64, targetSizeY: 64,
                        shiftX: 0, shiftY: 0 }, function (result) {
                        if (result.error || map.size.x !== 64 || map.size.y !== 64)
                            fail("mapchangesize " + JSON.stringify(result) + " size=" + JSON.stringify(map.size));
                        else { preparation = false; resizePending = true; }
                    });
                }
                return;
            }
            if (started) return;
            started = true;
            if (probe) { try { metadata(); probeNext(0, []); } catch (error) { fail(String(error)); } return; }
            if (playable) { sourceRides = map.rides.map(function (ride) { return ride.id; }); preparation = true; }
            else populate();
        });
        function populate() {
            try { park.name = "Frontier Outpost"; terrain(); scenery(); createAt(0); }
            catch (error) { fail(String(error)); }
        }
    }
});
