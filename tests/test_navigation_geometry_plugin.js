const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Exercise actual plugin discovery. Each tile is a committed OpenRCT2-style
// element; the assertions concern exported physical volumes, not an invented
// navigation mask.
const tiles = new Map();
function at(x, y) {
    const key = `${x},${y}`;
    if (!tiles.has(key)) tiles.set(key, [{ type: 'surface', baseHeight: 14, baseZ: 112,
        waterHeight: 0, surfaceObject: 1, slope: 0 }]);
    return tiles.get(key);
}
const rides = [
    { id: 1, name: 'Corkscrew', type: 19, classification: 'ride', object: { identifier: 'rct2.ride.cstl' } },
    { id: 2, name: 'Food Stall', type: 28, classification: 'stall', object: { identifier: 'rct2.ride.food' } },
    { id: 3, name: 'First Aid', type: 48, classification: 'facility', object: { identifier: 'rct2.ride.aid' } },
];
function track(x, y, ride, trackType, baseZ, sequence = 0, direction = 0, occupiedQuadrants = 15) {
    at(x, y).push({ type: 'track', ride, trackType, baseHeight: baseZ / 8,
        baseZ, clearanceZ: baseZ + 48, sequence, direction, occupiedQuadrants });
}
track(1, 1, 1, 0, 160);           // elevated straight
track(2, 1, 1, 16, 160, 2, 1, 7); // elevated left five-tile curve, rotated quarters
track(3, 1, 1, 17, 128, 3, 2, 11); // low right curve
track(4, 1, 1, 4, 136, 0, 2);    // 25 degree incline, clear at its high end
track(5, 1, 1, 1, 112);          // station
track(6, 1, 2, 0, 160);          // deliberate internal type-zero shop tile
track(7, 1, 3, 262, 112);        // ordinary facility tile
at(8, 1).push({ type: 'entrance', ride: 1, baseHeight: 14, baseZ: 112,
    clearanceZ: 160, direction: 1, occupiedQuadrants: 15 });
track(9, 1, 1, 18, 160);         // unknown coaster shape remains conservative
track(10, 1, 1, 16, 160, 2, 1, 15);
at(10, 1).at(-1).isGhost = true; // construction preview is excluded
track(11, 1, 1, 50, 160);        // unverified one-tile curve remains conservative

const sent = [], responses = [];
let socket;
const sandbox = {
    map: { size: { x: 12, y: 4 }, rides, getRide(id) { return rides.find(r => r.id === id); },
        getTile(x, y) { const elements = at(x, y); return { numElements: elements.length,
            getElement(n) { return elements[n]; } }; } },
    objectManager: { getAllObjects() { return []; } },
    network: { mode: 'server', currentPlayer: { id: 1 }, players: [{ id: 1 }], createSocket() {
        socket = { handlers: {}, on(kind, callback) { this.handlers[kind] = callback; },
            connect(_port, _host, callback) { callback(); },
            write(line) { const message = JSON.parse(line); sent.push(message);
                responses.push(JSON.stringify({ v: 1, kind: 'world.ack', session: message.session,
                    payload: { op_id: message.op_id, accepted: true } }) + '\n');
            }, destroy() {} };
        return socket;
    } },
    rtsBridge: { version: 5, assetVersion: 4, invalidateAnimation() {}, setBuildingAnimations() {}, applySnapshot() {}, clearSnapshot() {}, hitTest() {},
        actorScreenPosition() { return null; } },
    ui: { tileSelection: { tiles: [] }, openWindow() { return { findWidget() { return { text: '' }; } }; },
        registerShortcut() {}, registerViewportInteraction() {}, activateTool() {}, showError() {} },
    context: { registerAction() {}, subscribe() {}, executeAction() {} },
    console: { log() {} }, registerPlugin(plugin) { plugin.main(); },
};
vm.runInNewContext(fs.readFileSync('openrct2-plugin/rts-bridge.js', 'utf8'), sandbox);
while (responses.length) socket.handlers.data(responses.shift());
const entities = sent.filter(m => m.kind === 'world.snapshot.chunk').flatMap(m => m.payload.entities || []);
const volumeAt = x => entities.flatMap(e => e.collision.volumes || [])
    .filter(v => v.rect.x >= x * 32 && v.rect.x < (x + 1) * 32)
    .sort((a, b) => a.rect.x - b.rect.x || a.rect.y - b.rect.y);
assert.equal(volumeAt(1)[0].base_z, 160);
assert.equal(volumeAt(1)[0].clearance_z, 168);
assert.equal(volumeAt(2)[0].base_z, 160);
assert.equal(volumeAt(2)[0].occupied_quadrants, 7, 'already rotated OpenRCT2 occupancy is retained');
assert.match(volumeAt(2)[0].source, /flat_curve_unrepresented_supports$/);
assert.equal(volumeAt(3)[0].base_z, 128, 'low curve stays in unit clearance');
assert.equal(volumeAt(4).length, 4, 'sloped rail uses native-width strips');
assert.deepEqual(volumeAt(4).map(v => v.base_z), [136, 140, 144, 148]);
assert.ok(volumeAt(4).every(v => v.rect.width === 8 && v.occupied_quadrants === 15));
assert.equal(volumeAt(5)[0].base_z, 112);
assert.match(volumeAt(5)[0].source, /station_approx$/);
assert.equal(volumeAt(6)[0].base_z, 112, 'shop cannot inherit the thin-rail approximation');
assert.match(volumeAt(6)[0].source, /solid_building$/);
assert.match(volumeAt(7)[0].source, /solid_building$/);
assert.match(volumeAt(8)[0].source, /ride_entrance_exit$/);
assert.equal(volumeAt(8)[0].base_z, 112);
assert.match(volumeAt(9)[0].source, /unknown_track_shape$/);
assert.equal(volumeAt(10).length, 0, 'ghost track has no authoritative physical volume');
assert.equal(volumeAt(11)[0].base_z, 112);
assert.match(volumeAt(11)[0].source, /unknown_track_shape$/);
assert.equal(entities.filter(e => e.kind === 'ride').length, 1,
    'one ride retains one combat identity despite different physical segments');
console.log('navigation geometry export validation passed');
