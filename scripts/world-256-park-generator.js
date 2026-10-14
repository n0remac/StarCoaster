/* Deterministic, test-only 256x256 saved park. Licensed source stays local. */
registerPlugin({ name: "World 256 Park Generator", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    let phase = "demolish", busy = false, rides = map.rides.map(function (ride) { return ride.id; });
    const sourceRides = rides.length;
    function fail(message) { console.log("WORLD256_GENERATOR_FAILED " + message); phase = "failed"; }
    function resize(size, next) {
        busy = true;
        context.executeAction("mapchangesize", { targetSizeX: size, targetSizeY: size,
            shiftX: 0, shiftY: 0 }, function (result) {
            busy = false;
            if (result.error || map.size.x !== size || map.size.y !== size)
                fail("mapchangesize " + size + " " + JSON.stringify(result));
            else phase = next;
        });
    }
    context.subscribe("interval.tick", function () {
        if (network.mode !== "server" || busy || phase === "failed" || phase === "done") return;
        if (phase === "demolish") {
            if (rides.length) {
                const id = rides.shift(); busy = true;
                context.executeAction("ridedemolish", { ride: id, modifyType: 0 }, function (result) {
                    busy = false;
                    if (result.error) fail("ridedemolish " + id + " " + JSON.stringify(result));
                });
                return;
            }
            ["guest", "staff", "car"].forEach(function (kind) {
                map.getAllEntities(kind).forEach(function (entity) { entity.remove(); });
            });
            phase = "shrink";
        } else if (phase === "shrink") resize(64, "grow");
        else if (phase === "grow") resize(256, "populate");
        else if (phase === "populate") {
            try {
                let extra = 0;
                for (let y = 0; y < 256; y++) for (let x = 0; x < 256; x++) {
                    const tile = map.getTile(x, y);
                    for (let i = tile.numElements - 1; i >= 0; i--)
                        if (tile.getElement(i).type !== "surface") { tile.removeElement(i); extra++; }
                    const surface = tile.getElement(0);
                    if (surface.type !== "surface") throw new Error("missing surface at " + x + "," + y);
                    surface.baseHeight = 14;
                    surface.clearanceHeight = 14;
                    surface.slope = 0;
                    surface.waterHeight = 0;
                }
                const identifier = "rct2.scenery_small.tap";
                let object = objectManager.getAllObjects("small_scenery").find(function (entry) {
                    return entry.identifier === identifier;
                });
                if (!object) { objectManager.load(identifier); object = objectManager.getAllObjects("small_scenery")
                    .find(function (entry) { return entry.identifier === identifier; }); }
                if (!object) throw new Error("boundary scenery unavailable");
                [[8, 8], [247, 247]].forEach(function (point) {
                    const tile = map.getTile(point[0], point[1]);
                    tile.insertElement(tile.numElements);
                    const element = tile.getElement(tile.numElements - 1);
                    element.type = "small_scenery"; element.baseHeight = 14;
                    element.clearanceHeight = 26; element.object = object.index;
                    element.quadrant = 0;
                });
                park.name = "World 256 Scale Fixture";
                if (map.size.x !== 256 || map.size.y !== 256 || map.rides.length !== 0
                    || map.getTile(8, 8).numElements !== 2 || map.getTile(247, 247).numElements !== 2)
                    throw new Error("generated park verification failed");
                console.log("WORLD256_GENERATED " + JSON.stringify({ size: map.size, source_rides: sourceRides,
                    removed_elements: extra, markers: [[8, 8], [247, 247]] }));
                phase = "save";
            } catch (error) { fail(String(error)); }
        } else if (phase === "save") {
            context.saveGame({ filename: "world-256-scale" });
            phase = "done";
        }
    });
}});
